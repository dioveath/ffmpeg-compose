import time
import threading
import tempfile
import requests
import subprocess
import shlex
import os
import logging

from typing import List, Dict, Any, Optional, Union, Tuple

# Configure logging
logger = logging.getLogger(__name__)


def validate_ffmpeg_installed() -> bool:
    """Check if FFmpeg is installed and available in the system PATH"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                               stdout=subprocess.PIPE, 
                               stderr=subprocess.PIPE, 
                               text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def validate_file_exists(file_path: str) -> bool:
    """Check if a file exists"""
    return os.path.isfile(file_path)


def build_ffmpeg_command(input_files: List[str], 
                        output_file: str, 
                        options: Dict[str, Any], 
                        global_options: List[str]) -> List[str]:
    """Build the FFmpeg command from the provided options
    
    Args:
        input_files: List of input file paths
        output_file: Output file path
        options: Dictionary of FFmpeg options
        global_options: List of global FFmpeg options
        
    Returns:
        List of command arguments ready for subprocess execution
    """
    command = ['ffmpeg']
    
    # Add global options
    if global_options:
        for opt in global_options:
            # Handle options that might contain spaces
            if ' ' in opt and not (opt.startswith('"') or opt.startswith("'")):
                command.extend(shlex.split(opt))
            else:
                command.append(opt)
                
    import multiprocessing
    num_threads = multiprocessing.cpu_count()
    global_options.extend(["-filter_complex_threads", str(num_threads)])
    
    # Add input files
    for input_file in input_files:
        if isinstance(input_file, list):
            path_from_list = input_file[-1]
            options_for_this_input = input_file[:-1]
            command.extend(options_for_this_input)
            command.extend(['-i', str(path_from_list)])
        elif isinstance(input_file, str):
            command.extend(['-i', input_file])
    
    # Add specific options
    for option, value in options.items():
        if isinstance(value, bool):
            if value:
                command.append(f'-{option}')
        elif isinstance(value, list):
            for item in value:
                command.extend([f'-{option}', str(item)])
        elif value is None:
            # Skip None values
            continue
        else:
            command.extend([f'-{option}', str(value)])
    
    # Add output file
    command.append(output_file)
    
    return command


def download_remote_file_to_temp(url: str, temp_files_list: List[str]) -> str:
    """Download a remote file to a temporary location
    Args:
        url: URL of the remote file
        temp_files_list: List to store temporary file paths
    Returns:
        Path to the downloaded temporary file
    Raises:
        requests.exceptions.RequestException: If there's an error downloading the file
        IOError: If there's an error creating the temporary file
        ValueError: If the content type of the remote file is unsupported
    """

    logger.info(f"Downloading remote file: {url}")
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()  # Raise an exception for HTTP errors
    
        parsed_url = urlparse(url)
        original_filename = os.path.basename(parsed_url.path)
        _, ext = os.path.splitext(original_filename)
        if not ext:
            content_type = response.headers.get('Content-Type', '').lower()
            if 'application/x-subrip' in content_type:
                ext = '.srt'
            elif 'text/plain' in content_type and ('.ass' in url or '.ssa' in url):
                ext = '.ass'
            elif 'text/vtt' in content_type:
                ext = '.vtt'
            else:
                raise ValueError("Unsupported content type for remote file.")

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext, mode='wb')
        try:
            for chunk in response.iter_content(chunk_size=8192):
                temp_file.write(chunk)
            temp_file.close()
            temp_files_list.append(temp_file.name)
            logger.info(f"Downloaded remote file to temporary location: {temp_file.name}")
            return temp_file.name.replace('\\', '/')
        except IOError as e:
            logger.error(f"Error creating temporary file: {e}")
            temp_file.close()
            if os.path.exists(temp_file.name):
                os.remove(temp_file.name)
            raise IOError(f"Error creating temporary file: {e}")

    except requests.exceptions.RequestException as e:
        logger.error(f"Error downloading remote file: {e}")
        raise e


def format_command_for_display(command: List[str]) -> str:
    """Format a command list into a readable string for display"""
    formatted_cmd = []
    for item in command:
        # Add quotes around items with spaces
        if ' ' in item and not (item.startswith('"') or item.startswith("'")):
            formatted_cmd.append(f'"{item}"')
        else:
            formatted_cmd.append(item)
    
    return ' '.join(formatted_cmd)


def parse_ffmpeg_progress(stderr_line: str, detected_duration: Optional[float] = None) -> Tuple[Optional[Dict[str, Any]], Optional[float]]:
    """Parse FFmpeg progress information from stderr output
    Extracts time, frame, and calculates progress percentage from FFmpeg stderr output.
    Args:
        stderr_line: A line of FFmpeg stderr output
    Returns:
        Dictionary with progress information or None if no progress info found
    """

    # Try to detect the duration from FFmpeg output
    if 'Duration:' in stderr_line and detected_duration is None:
        try:
            duration_str = stderr_line.split('Duration:')[1].split(',')[0].strip()
            duration_parts = duration_str.split(':')
            if len(duration_parts) == 3:
                hours, minutes, seconds = duration_parts
                # Handle seconds with milliseconds
                if '.' in seconds:
                    seconds, ms = seconds.split('.')
                    detected_duration = (int(hours) * 3600) + (int(minutes) * 60) + int(seconds) + (int(ms) / 100)
                else:
                    detected_duration = (int(hours) * 3600) + (int(minutes) * 60) + int(seconds)
                logger.info(f"Detected video duration: {detected_duration} seconds")
                return None, detected_duration
        except (IndexError, ValueError):
            pass
    
    if 'time=' in stderr_line:
        try:
            # Extract time information
            time_str = stderr_line.split('time=')[1].split(' ')[0]
            
            # Calculate progress percentage based on time
            # Convert time string (HH:MM:SS.MS) to seconds for calculation
            time_parts = time_str.split(':')
            if len(time_parts) == 3:
                hours, minutes, seconds = time_parts
                # Handle seconds with milliseconds
                if '.' in seconds:
                    seconds, ms = seconds.split('.')
                    total_seconds = (int(hours) * 3600) + (int(minutes) * 60) + int(seconds) + (int(ms) / 100)
                else:
                    total_seconds = (int(hours) * 3600) + (int(minutes) * 60) + int(seconds)
                
                # Calculate progress percentage using detected duration if available
                if detected_duration and detected_duration > 0:
                    progress_percent = min(100.0, (total_seconds / detected_duration) * 100)
                else:
                    # Fallback to a reasonable estimate if duration is unknown
                    max_duration = 300  # 5 minutes in seconds as a reasonable fallback
                    progress_percent = min(100.0, (total_seconds / max_duration) * 100)
                
                # Ensure we're not stuck at 0% by setting a minimum progress value
                # once we have time information
                if progress_percent < 0.1 and total_seconds > 0:
                    progress_percent = 0.1
            else:
                progress_percent = 0.0
            
            # Extract frame information if available
            frame = None
            if 'frame=' in stderr_line:
                frame_str = stderr_line.split('frame=')[1].split(' ')[0].strip()
                try:
                    frame = int(frame_str)
                    # Use frame count as an additional progress indicator
                    if frame > 0 and progress_percent == 0.0:
                        progress_percent = 0.1  # At least show some progress if frames are being processed
                except ValueError:
                    pass
            
            # Extract speed information if available
            speed = None
            if 'speed=' in stderr_line:
                speed_str = stderr_line.split('speed=')[1].split(' ')[0]
                speed = speed_str
            
            return {
                'time': time_str,
                'frame': frame,
                'speed': speed,
                'progress_percent': round(progress_percent, 2)
            }, detected_duration
        except (IndexError, ValueError):
            pass
    
    return None, detected_duration


class ProgressFfmpeg(threading.Thread):
    def __init__(self, vid_duration_seconds, progress_update_callback):
        threading.Thread.__init__(self, name="ProgressFfmpeg")
        self.stop_event = threading.Event()
        self.output_file = tempfile.NamedTemporaryFile(mode="w+", delete=False)
        self.vid_duration_seconds = vid_duration_seconds
        self.progress_update_callback = progress_update_callback

    def run(self):
        while not self.stop_event.is_set():
            latest_progress = self.get_latest_ms_progress()
            if latest_progress is not None:
                completed_percent = latest_progress / self.vid_duration_seconds
                self.progress_update_callback(completed_percent)
            time.sleep(1)

    def get_latest_ms_progress(self):
        lines = self.output_file.readlines()

        if lines:
            for line in lines:
                if "out_time_ms" in line:
                    out_time_ms_str = line.split("=")[1].strip()
                    if out_time_ms_str.isnumeric():
                        return float(out_time_ms_str) / 1000000.0
                    else:
                        # Handle the case when "N/A" is encountered
                        return None
        return None

    def stop(self):
        self.stop_event.set()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args, **kwargs):
        self.stop()


def get_media_duration_seconds(video_url):
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            # "-select_streams", "v:0",
            "-show_entries", "stream=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_url
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return float(result.stdout.strip())
    except subprocess.CalledProcessError as e:
        logger.error(f"Error getting video duration: {e}")
        return None