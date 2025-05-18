import os
import json
from datetime import timedelta
import subprocess
from typing import List, Dict, Any
from celery import Celery
import logging
from minio import Minio
from ffmpeg_utils import build_ffmpeg_command, format_command_for_display, validate_ffmpeg_installed, parse_ffmpeg_progress

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Check if FFmpeg is installed
if not validate_ffmpeg_installed():
    logger.error("FFmpeg is not installed or not found in PATH. Please install FFmpeg to use this application.")

broker_url = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
result_backend = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')    

# Configure MinIO client
minio_client = Minio(
    os.environ.get('MINIO_ENDPOINT', 'localhost:9000'),
    access_key=os.environ.get('MINIO_ACCESS_KEY', 'minioadmin'),
    secret_key=os.environ.get('MINIO_SECRET_KEY', 'minioadmin'),
    secure=os.environ.get('MINIO_SECURE', 'False').lower() == 'true'
)

# Ensure bucket exists
bucket_name = os.environ.get('MINIO_BUCKET_NAME', 'video-storage')
try:
    if not minio_client.bucket_exists(bucket_name):
        minio_client.make_bucket(bucket_name)
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{bucket_name}/*"]
                }
            ]
        }
        policy_str = json.dumps(policy)
        minio_client.set_bucket_policy(bucket_name, policy_str)
        logger.info(f"Bucket '{bucket_name}' created and policy set.")
except Exception as e:
    logger.error(f"Failed to create or set policy for bucket '{bucket_name}': {str(e)}")

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
    process = None

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
        
        # Execute the command with progress tracking
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1
        )
        
        # Track progress
        progress_data = {
            'time': '00:00:00.00',
            'frame': 0,
            'progress_percent': 0.0,
            'status': 'processing'
        }
        
        # Update task state with initial progress
        self.update_state(
            state='PROGRESS',
            meta={
                'pid': process.pid,
                'progress': progress_data
            }
        )
        
        # Process output in real-time to track progress
        stderr_lines = []
        last_update_time = 0
        update_interval = 1.0  # Update progress at most once per second
        duration = None
        
        import time
        current_time = time.time()
        
        for line in iter(process.stderr.readline, ''):
            stderr_lines.append(line)
            # Parse progress information
            progress_info, detected_duration = parse_ffmpeg_progress(line, duration)
            
            if duration is None and detected_duration is not None:
                duration = detected_duration
            
            # Update progress data if new information is available
            if progress_info:
                progress_data.update(progress_info)
                
                # Limit how often we update the task state to avoid overwhelming Celery/Redis
                if current_time - last_update_time >= update_interval:
                    # Update task state with progress
                    self.update_state(
                        state='PROGRESS',
                        meta={
                            'progress': progress_data
                        }
                    )
                    logger.info(f"FFmpeg progress: {progress_data}")
                    last_update_time = current_time
            
            # Update current time for next iteration
            current_time = time.time()
        
        # Join stderr lines for error reporting
        stderr = '\n'.join(stderr_lines)
            
        # Wait for process to complete
        process.stderr.close()
        process.stdout.close()
        returncode = process.wait()
        
        # Get any remaining output
        stdout = ''
        stderr = ''
        
        if returncode != 0:
            logger.error(f"FFmpeg command failed with return code {returncode}")
            logger.error(f"Error output: {stderr}")
            return {
                'success': False,
                'error': stderr,
                'command': formatted_command,
                'return_code': returncode,
            }
        
        # Upload the processed file to MinIO
        object_name = os.path.basename(output_file)
        try:
            minio_client.fput_object(bucket_name, object_name, output_file)
            minio_public_endpoint = os.environ.get('MINIO_PUBLIC_ENDPOINT', 'http://localhost:9000')
            storage_url = f"{minio_public_endpoint}/{bucket_name}/{object_name}"
            # storage_url = minio_client.presigned_get_object(bucket_name, object_name, expires=timedelta(days=365*10))
            logger.info(f"File uploaded to MinIO: {storage_url}")
            
            # Remove local file after successful upload
            os.remove(output_file)
            logger.info(f"Local file removed: {output_file}")
            
            # Update progress to 100% for completed tasks
            progress_data['progress_percent'] = 100.0
            progress_data['status'] = 'completed'
            
            return {
                'success': True,
                'output_url': storage_url,
                'command': formatted_command,
                'message': 'FFmpeg processing and upload completed successfully',
                # 'progress': progress_data
            }
        except Exception as upload_error:
            logger.error(f"Failed to upload file to MinIO: {str(upload_error)}")
            # Update progress status for upload failure
            progress_data['status'] = 'upload_failed'
            
            return {
                'success': False,
                'error': f"Failed to upload file: {str(upload_error)}",
                'command': formatted_command,
                'progress': progress_data
            }
    
    except Exception as e:
        error_msg = str(e)
        logger.exception(f"Exception during FFmpeg processing: {error_msg}")
        # Set progress status for general failure
        if 'progress_data' in locals():
            progress_data['status'] = 'failed'
        else:
            progress_data = {
                'time': '00:00:00.00',
                'frame': 0,
                'progress_percent': 0.0,
                'status': 'failed'
            }
            
        return {
            'success': False,
            'error': error_msg,
            'command': format_command_for_display(command) if command else 'Command not built',
            'progress': progress_data
        }
    
    finally:
        if process is not None:
            try:
                if process.poll() is None:
                    process.terminate()
                    logger.info(f"Process {process.pid} terminated in finally block")
            except Exception as term_error:
                logger.error(f"Error terminating process: {term_error}")