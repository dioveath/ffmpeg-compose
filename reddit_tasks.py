import logging
import json
import subprocess
from pathlib import Path
from typing import Optional
from PIL import Image
from celery_worker import celery_app
from reddit_utils import create_fancy_thumbnail

logger = logging.getLogger(__name__)

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
    webhook_url: Optional[str] = None
):
    """Celery task to generate the Reddit intro video"""
    task_id = self.request.id
    result = {}
    logger.info(f"Starting Reddit intro task with ID: {task_id}")
    logger.info(f"resolution_x: {resolution_x}")
    logger.info(f"resolution_y: {resolution_y}")
    logger.info(f"duration: {duration}")
    logger.info(f"font: {font}")
    logger.info(f"font_color: {font_color}")
    logger.info(f"padding: {padding}")

    temp_assets_path = "temp/assets"
    Path(f"{temp_assets_path}/png").mkdir(parents=True, exist_ok=True)
    screenshot_width = int((resolution_x * 90) // 100)
    title_template = Image.open("assets/title_template.png")

    logger.info(f"Creating customized title image...")
    title_img = create_fancy_thumbnail(title_template, title, font_color, padding, subreddit=subreddit)
    title_img.save(f"{temp_assets_path}/png/title.png")

    output_path = f"{temp_assets_path}/png/reddit_intro.mp4"

    try:
        video_filter_args = (
            f"scale={resolution_x}:{resolution_y}:force_original_aspect_ratio=decrease,"
            f"pad={resolution_x}:{resolution_y}:(ow-iw)/2:(oh-ih)/2:color=black"
        )

        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-framerate", "30", "-i", f"{temp_assets_path}/png/title.png",
            # "-vf", f"scale={screenshot_width}:-1",
            "-vf", video_filter_args,
            "-c:v", "libx264",
            "-t", f"{duration}",
            "-pix_fmt", "yuv420p",
            "-r", "30",
            output_path
        ]

        logger.info(f"Running ffmpeg command: {' '.join(ffmpeg_cmd)}")

        subprocess.run(ffmpeg_cmd, check=True)

        result = {
            "task_id": task_id,
            "status": "COMPLETED",
            "message": "Reddit intro video generated successfully",
            "output_file": output_path
        }

        logger.info(f"Result: {json.dumps(result, indent=4)}")

    except subprocess.CalledProcessError as e:
        print(f"Error generating video: {e}")
        return None