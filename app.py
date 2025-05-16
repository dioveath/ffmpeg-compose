from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from celery.result import AsyncResult
import subprocess
import os

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
    """Get the status of a task"""
    task_result = AsyncResult(task_id, app=celery_app)
    
    result = {
        "task_id": task_id,
        "status": task_result.status,
    }
    
    if task_result.ready():
        if task_result.successful():
            result["result"] = task_result.result
        else:
            result["error"] = str(task_result.result)
    
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)