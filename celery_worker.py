import os
import subprocess
from typing import List, Dict, Any
from celery import Celery
import logging
from ffmpeg_utils import build_ffmpeg_command, format_command_for_display, validate_ffmpeg_installed

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Check if FFmpeg is installed
if not validate_ffmpeg_installed():
    logger.error("FFmpeg is not installed or not found in PATH. Please install FFmpeg to use this application.")

broker_url = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
result_backend = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')    

# Configure Celery
celery_app = Celery('celery_worker', broker=broker_url, backend=result_backend)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    include=['celery_worker']
)


@celery_app.task(bind=True)
def process_ffmpeg_task(self, input_files: List[str], output_file: str, 
                     options: Dict[str, Any], global_options: List[str]):
    """Celery task to process FFmpeg commands"""
    command = []
    try:
        # Log task start
        logger.info(f"Starting FFmpeg task with {len(input_files)} input files, output: {output_file}")
        
        # Ensure output directory exists
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
            logger.info(f"Created output directory: {output_dir}")
        
        # Build the FFmpeg command
        command = build_ffmpeg_command(
            input_files=input_files,
            output_file=output_file,
            options=options,
            global_options=global_options
        )
        
        # Format command for logging
        formatted_command = format_command_for_display(command)
        logger.info(f"Executing FFmpeg command: {formatted_command}")
        
        # Execute the command
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        stdout, stderr = process.communicate()
        
        if process.returncode != 0:
            logger.error(f"FFmpeg command failed with return code {process.returncode}")
            logger.error(f"Error output: {stderr}")
            return {
                'success': False,
                'error': stderr,
                'command': formatted_command,
                'return_code': process.returncode
            }
        
        logger.info(f"FFmpeg processing completed successfully: {output_file}")
        return {
            'success': True,
            'output_file': output_file,
            'command': formatted_command,
            'message': 'FFmpeg processing completed successfully'
        }
    
    except Exception as e:
        error_msg = str(e)
        logger.exception(f"Exception during FFmpeg processing: {error_msg}")
        return {
            'success': False,
            'error': error_msg,
            'command': format_command_for_display(command) if command else 'Command not built'
        }