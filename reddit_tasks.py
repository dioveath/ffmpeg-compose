import re
import logging
import json
import subprocess
from pathlib import Path
from typing import Optional
from PIL import Image
from celery_worker import celery_app
from reddit_utils import create_fancy_thumbnail
from ffmpeg_utils import ProgressFfmpeg
from webhook_utils import send_webhook_task
from celery.result import AsyncResult
from celery import states

from minioclient_utils import minio_client, bucket_name, minio_public_endpoint

logger = logging.getLogger(__name__)

def clean_text_to_folder_name(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[\s!"\'-]+', '_', text)
    text = re.sub(r'[^a-z0-0_]', '', text)
    text = re.sub(r'_+', '_', text)
    text = text.strip('_')
    return text    


@celery_app.task(bind=True)
def process_reddit_intro_task(
    self,
    subreddit: str,
    title: str,
    resolution_x: int,
    resolution_y: int,
    duration: int,
    font: str,
    font_color: str,
    padding: int,
    audio_url: Optional[str] = None,
    background_video_url: Optional[str] = None,
    webhook_url: Optional[str] = None
):
    """Celery task to generate the Reddit intro video"""
    task_id = self.request.id
    logger.info(f"Starting Reddit intro task with ID: {task_id}")
    logger.info(f"resolution_x: {resolution_x}")
    logger.info(f"resolution_y: {resolution_y}")
    logger.info(f"duration: {duration}")
    logger.info(f"font: {font}")
    logger.info(f"font_color: {font_color}")
    logger.info(f"padding: {padding}")

    result = {}
    TEMP_ASSETS_PATH = "temp/assets"
    temp_folder = clean_text_to_folder_name(title)
    Path(f"{TEMP_ASSETS_PATH}/{temp_folder}").mkdir(parents=True, exist_ok=True)
    screenshot_width = int((resolution_x * 90) // 100)
    title_template = Image.open("assets/title_template.png")

    logger.info(f"Creating customized title image...")
    title_img = create_fancy_thumbnail(title_template, title, font_color, padding, subreddit=subreddit)
    title_img.save(f"{TEMP_ASSETS_PATH}/{temp_folder}/title.png")

    output_path = f"{TEMP_ASSETS_PATH}/{temp_folder}/reddit_intro.mp4"

    try:
        if background_video_url is None:
            background_video_url = "https://storage.charichagaming.com.np/video-storage/Satisfying%20Cake%20Compilation-satisfying-cake.mp4"

        def update_celery_progress(completed_percent: float):
            progress = int(completed_percent * 100)
            logger.info(f"Progress: {progress}%")
            if hasattr(self, "update_state"): # check if running in a Celery task (context)
                self.update_state(
                    task_id=task_id,
                    state="PROGRESS",
                    meta={
                        "task_id": task_id,
                        "status": "processing",
                        "progress": progress,
                        "message": "Generating Reddit intro video..."
                    }
                )
        update_celery_progress(0.0)

        with ProgressFfmpeg(float(duration), update_celery_progress) as progress_monitor:
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-stream_loop", "-1", "-i", background_video_url,
                "-loop", "1", "-framerate", "30", "-i", f"{TEMP_ASSETS_PATH}/{temp_folder}/title.png"
            ]

            fade_in_duration = 1
            fade_out_duration = 2
            filter_complex_args = [
                f"[0:v]scale={resolution_x}:{resolution_y}:force_original_aspect_ratio=increase,crop={resolution_x}:{resolution_y}[bg]",
                f"[1:v]scale={screenshot_width}:-1[title_scaled]",
                f"[bg][title_scaled]overlay=(W-w)/2:(H-h)/2,fade=t=in:st=0:d={fade_in_duration},fade=t=out:st={{fade_out_start}}:d=3[outv]"
            ]

            if audio_url:
                probe_cmd = [
                    "ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_url
                ]
                probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
                audio_duration = float(probe_result.stdout.strip())
                logger.info(f"Audio duration: {audio_duration}")

                duration = min(audio_duration, duration) + fade_in_duration
                fade_out_start = duration + fade_out_duration
                duration += fade_out_duration

                logger.info(f"Total video duration: {duration}")

                ffmpeg_cmd.extend(["-i", audio_url])
                filter_complex_args.extend([f"[2:a]adelay=2000|2000[outa]"])
                ffmpeg_cmd.extend(["-map", "[outa]", "-c:a", "aac"])
            else:
                fade_out_start = duration - 3                

            filter_complex_args[2] = filter_complex_args[2].format(fade_out_start=fade_out_start)
            ffmpeg_cmd.extend([
                "-filter_complex", ";".join(filter_complex_args),
                "-map", "[outv]",
                "-c:v", "libx264",
                "-t", f"{duration}",
                "-pix_fmt", "yuv420p",
                "-r", "30",
                "-progress", progress_monitor.output_file.name,
                output_path
            ])
            
            # ffmpeg_cmd = [
            #     "ffmpeg", "-y",
            #     "-stream_loop", "-1", "-i", background_video_url,
            #     "-loop", "1", "-framerate", "30", "-i", f"{TEMP_ASSETS_PATH}/{temp_folder}/title.png",
            #     "-filter_complex", "".join(filter_complex_args),
            #     "-map", "[outv]",
            #     "-c:v", "libx264",
            #     "-t", f"{duration}",
            #     "-pix_fmt", "yuv420p",
            #     "-r", "30",
            #     "-progress", progress_monitor.output_file.name,
            #     output_path
            # ]
            logger.info(f"Running ffmpeg command: {' '.join(ffmpeg_cmd)}")
            process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            stdout, stderr = process.communicate()

            if process.returncode != 0:
                error_msg = f"Error generating video: {stderr}"
                raise subprocess.CalledProcessError(returncode=process.returncode, cmd=ffmpeg_cmd, output=stdout, stderr=stderr)

            update_celery_progress(1.0)    
            logger.info(f"Video generated successfully: {output_path}")

            minio_client.fput_object(bucket_name, f"{temp_folder}/reddit_intro.mp4", output_path)
            output_url = f"{minio_public_endpoint}/{bucket_name}/{temp_folder}/reddit_intro.mp4"
            logger.info(f"Video uploaded to MinIO: {output_url}")
            result["output_url"] = output_url
            
            self.update_state(
                state=states.SUCCESS,
                meta={
                    "task_id": task_id,
                    "status": "completed",
                    "output_url": output_url,                    
                    "message": "Reddit intro video generated successfully"
                }
            )

            result = {
                "task_id": task_id,
                "status": "completed",
                "output_url": output_url,
                "message": "Reddit intro video generated successfully"                
            }
            logger.info(f"Result: {json.dumps(result, indent=4)}")
            return result
    except subprocess.CalledProcessError as e:
        logger.error(f"Error generating video: {e}")
        logger.error(f"FFmpeg stderr output: {e.stderr}")
        self.update_state(
            state=states.FAILURE,
            meta={
                "task_id": task_id,
                "status": "failed",
                "stderr": e.stderr,
                # "progress": self.request.meta.get("progress", 0),
                "message": "Error generating Reddit intro video"
            }
        )
    except Exception as e:
        logger.error(f"Error generating video: {e}")
        self.update_state(
            state=states.FAILURE,
            meta={
                "task_id": task_id,
                "status": "failed",
                # "progress": self.request.meta.get("progress", 0),
                "message": "Error generating Reddit intro video"
            }
        )
    finally:
        logger.info(f"Cleaning up temporary assets...")
        # shutil.rmtree(temp_assets_path)
        logger.info(f"Cleaned up temporary assets")

        if webhook_url:
            current_task_result = AsyncResult(task_id, app=celery_app)
            payload = {
                "task_id": task_id,
                "task_state": current_task_result.state,
                "task_info": current_task_result.info,
                "result": result
            }
            send_webhook_task(webhook_url, payload, task_id)
