from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from celery.result import AsyncResult
import subprocess
import os
import logging

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


@app.get("/")
async def root():
    return {"message": "FFmpeg Compose API is running"}


@app.post("/compose")
async def compose_ffmpeg(options: FFmpegOptions):
    """Endpoint to compose and execute FFmpeg commands"""
    try:
        # Submit the task to Celery
        task = process_ffmpeg_task.delay(
            input_files=options.input_files,
            output_file=options.output_file,
            options=options.options,
            global_options=options.global_options
        )
        
        return {"task_id": task.id, "status": "Processing"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    """Get the status of a task with progress information"""
    task_result = AsyncResult(task_id, app=celery_app)
    
    result = {
        "task_id": task_id,
        "status": task_result.status,
    }
    
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)