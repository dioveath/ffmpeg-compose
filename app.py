from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from celery.result import AsyncResult
import subprocess
import os
import logging
import requests

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from celery_worker import celery_app, process_ffmpeg_task

app = FastAPI(title="FFmpeg Compose API", description="API for processing FFmpeg commands")


class FFmpegOptions(BaseModel):
    """Pydantic model for validating FFmpeg command options"""
    input_files: List[str] = Field(..., description="List of input file paths")
    output_file: str = Field(..., description="Output file path")
    options: Dict[str, Any] = Field(default_factory=dict, description="FFmpeg command options")
    global_options: List[str] = Field(default_factory=list, description="Global FFmpeg options")
    webhook_url: Optional[str] = Field(default=None, description="Webhook URL to call upon task completion")


@app.get("/")
async def root():
    return {"message": "FFmpeg Compose API is running"}

@app.get("/caption_fonts")
async def list_caption_fonts():
    """Endpoint to list available caption fonts"""
    try:
        result = subprocess.run(['fc-list'], capture_output=True, text=True, check=True)
        font_names = set()

        for line in result.stdout.splitlines():
            if ':' not in line:
                continue

            name_part = line.split(':', 2)[1].strip()
            for name in name_part.split(','):
                cleaned_name = name.strip()
                if cleaned_name:
                    font_names.add(cleaned_name)

        return {"fonts": sorted(font_names)}
    except subprocess.CalledProcessError as e:
        logger.error(f"Error listing caption fonts: {str(e)}")
        raise HTTPException(status_code=500, detail="Error listing caption fonts")
    except Exception as e:
        logger.error(f"Unexpected error listing caption fonts: {str(e)}")
        raise HTTPException(status_code=500, detail="Unexpected error listing caption fonts")
        

@app.post("/compose")
async def compose_ffmpeg(options: FFmpegOptions):
    """Endpoint to compose and execute FFmpeg commands"""
    try:
        # Submit the task to Celery
        task = process_ffmpeg_task.delay(
            input_files=options.input_files,
            output_file=options.output_file,
            options=options.options,
            global_options=options.global_options,
            webhook_url=options.webhook_url
        )
        
        return {"task_id": task.id, "status": "PROCESSING"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tasks/{task_id}", status_code=200)
async def get_task_status(task_id: str):
    """Get the status of a task with progress information"""
    # Create AsyncResult object for the task
    task_result = AsyncResult(task_id, app=celery_app)
    
    # Initialize result dictionary
    result = {
        "task_id": task_id,
        "status": task_result.status,
    }
    
    # Check if the task exists in the backend
    # Note: Celery doesn't provide a direct way to check if a task exists
    # A task with status PENDING could be either a non-existent task or a task that hasn't started yet
    # We'll use a heuristic approach to determine if a task likely doesn't exist
    
    # If the task is PENDING and has no task_name, it's likely that the task doesn't exist
    # This is not 100% reliable but provides a reasonable check
    if task_result.state == 'PENDING' and not hasattr(task_result, 'task_name'):
        # Check if this task ID was ever submitted through our API
        # You could implement a more robust solution by tracking task IDs in a database
        try:
            # Try to get more information about the task
            # If the task doesn't exist, this won't provide any additional information
            if not task_result.info:
                logger.warning(f"Task with ID {task_id} not found or no longer exists in the backend")
                raise HTTPException(status_code=404, detail=f"Task with ID {task_id} not found")
        except Exception as e:
            # If there's an exception while trying to get task info, it likely doesn't exist
            if "Task with ID" in str(e):
                raise e
            logger.error(f"Error checking task {task_id}: {str(e)}")
            raise HTTPException(status_code=404, detail=f"Task with ID {task_id} not found")
    
    # Include progress information if available
    if task_result.state == 'PROGRESS' and task_result.info:
        if 'progress' in task_result.info:
            result["progress"] = task_result.info['progress']
            # Log progress information for debugging
            logger.info(f"Task {task_id} progress: {task_result.info['progress']}")
    
    # Handle different task states
    if task_result.ready():
        if task_result.successful():
            result["result"] = task_result.result
            # If the task is successful but doesn't have progress info in the result
            # add a completed progress indicator
            if 'progress' not in result and task_result.result and isinstance(task_result.result, dict):
                if 'progress' in task_result.result:
                    result["progress"] = task_result.result['progress']
        else:
            result["error"] = str(task_result.result)
            # Add failed status to progress if available
            if 'progress' not in result:
                result["progress"] = {
                    'status': 'failed',
                    'progress_percent': 0.0
                }
    elif task_result.state == 'PENDING':
        # Task hasn't started yet
        result["progress"] = {
            'status': 'pending',
            'progress_percent': 0.0
        }
    
    return result


@app.delete("/tasks/{task_id}", status_code=200)
async def stop_task(task_id: str):
    """Stop a running task"""
    # Create AsyncResult object for the task
    task_result = AsyncResult(task_id, app=celery_app)
    
    # Check if the task exists
    if task_result.state == 'PENDING' and not hasattr(task_result, 'task_name'):
        try:
            if not task_result.info:
                logger.warning(f"Task with ID {task_id} not found or no longer exists in the backend")
                raise HTTPException(status_code=404, detail=f"Task with ID {task_id} not found")
        except Exception as e:
            if "Task with ID" in str(e):
                raise e
            logger.error(f"Error checking task {task_id}: {str(e)}")
            raise HTTPException(status_code=404, detail=f"Task with ID {task_id} not found")
    
    # Check if the task is already completed
    if task_result.ready():
        return {
            "task_id": task_id,
            "status": task_result.status,
            "message": "Task already completed, cannot be stopped"
        }
    
    pid = None
    if task_result.info and isinstance(task_result.info, dict) and 'pid' in task_result.info:
        pid = task_result.info['pid']
    
    # Revoke the task
    task_result.revoke(terminate=True, signal='SIGTERM')
    logger.info(f"Task {task_id} has been stopped")

    if pid:
        try:
            import os
            import signal
            os.kill(pid, signal.SIGTERM)
            logger.info(f"Sent SIGTERM to FFmpeg process with PID {pid}")
        except ProcessLookupError:
            logger.warning(f"Process with PID {pid} not found, may have already terminated")
        except Exception as e:
            logger.error(f"Error terminating FFmpeg process: {str(e)}")
    
    return {
        "task_id": task_id,
        "status": "REVOKED",
        "message": "Task has been stopped successfully"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)