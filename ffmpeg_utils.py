import subprocess
import shlex
from typing import List, Dict, Any, Optional, Union
import os


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
    
    # Add input files
    for input_file in input_files:
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


def parse_ffmpeg_progress(stderr_line: str) -> Optional[Dict[str, Any]]:
    """Parse FFmpeg progress information from stderr output"""
    if 'time=' in stderr_line:
        try:
            # Extract time information
            time_str = stderr_line.split('time=')[1].split(' ')[0]
            # Extract frame information if available
            frame = None
            if 'frame=' in stderr_line:
                frame_str = stderr_line.split('frame=')[1].split(' ')[0]
                try:
                    frame = int(frame_str)
                except ValueError:
                    pass
            
            return {
                'time': time_str,
                'frame': frame
            }
        except (IndexError, ValueError):
            pass
    
    return None