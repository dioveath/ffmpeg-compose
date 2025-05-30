import requests
import json
import time
import sys
import signal
import atexit

# API endpoint
BASE_URL = "http://localhost:5200"


# Global variable to store the current task ID
current_task_id = None


def cleanup():
    """Cleanup function to stop any running FFmpeg task"""
    global current_task_id
    if current_task_id:
        try:
            print(f"\nStopping task {current_task_id}...")
            response = requests.delete(f"{BASE_URL}/tasks/{current_task_id}")
            if response.status_code == 200:
                print("Task stopped successfully.")
            else:
                print(f"Failed to stop task: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"Error stopping task: {e}")


def signal_handler(sig, frame):
    """Handle termination signals"""
    print("\nReceived termination signal. Cleaning up...")
    cleanup()
    sys.exit(0)


def test_compose_endpoint():
    """Test the /compose endpoint with a sample FFmpeg command"""
    # Sample request data
    W = 1080
    H = 1920
    data = {
        # "input_files": ["http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/Sintel.mp4"],
        "input_files": [
            "https://drive.google.com/uc?export=download&id=1ATipDW3BKwtVGmC1hG6CKQ7wcsYYEvcS"
        ],
        "output_file": "test2.mp4",
        "options": {
            "filter_complex": f"[0:v]scale=w='if(gte(iw/ih,{W}/{H}), -2, {W})':h='if(gte(iw/ih,{W}/{H}), {H}, -2)',setsar=1[scaled_cover];"
            + f"[scaled_cover]crop=w={W}:h={H}:x='(iw-{W})/2':y='(ih-{H})/2',setsar=1[cropped_video]",
            "map": ["[cropped_video]", "0:a?"],
            "c:v": "libx264",
            "crf": 28,
            "preset": "veryfast",
            "c:a": "aac",
            "b:a": "128k",
        },
        "global_options": ["-y"],
    }

    new_data = {
        "input_files": [
            "https://drive.google.com/uc?export=download&id=1ATipDW3BKwtVGmC1hG6CKQ7wcsYYEvcS"
        ],
        "output_file": "output.mp4",
        "options": {
            "c:v": "libx264",
            "preset": "medium",
            "crf": 23,
            "pix_fmt": "yuv420p",
            "c:a": "aac",
            "b:a": "128k",
            "filter_complex": "[0:v]scale=w='if(gte(iw/ih,1080/1920),-2,1080)':h='if(gte(iw/ih,1080/1920),1920,-2)',setsar=1,crop=w=1080:h=1920:x='(iw-1080)/2':y='(ih-1920)/2',format=yuv420p,setsar=1[sc_v0];[sc_v0]drawtext=fontfile='/usr/share/fonts/custom/DejaVuSans.ttf':text='ugc agencies got you broke?':fontsize=35:fontcolor=white:x=(w-text_w)/2:y=h*0.15:box=1:boxcolor=black@0.6:boxborderw=5, drawtext=fontfile='/usr/share/fonts/custom/DejaVuSans.ttf':text='$6k a month for content? that'\\\\\\''s robbin'\\\\\\'' season.':fontsize=28:fontcolor=white:x=(w-text_w)/2:y=h*0.80:box=1:boxcolor=black@0.6:boxborderw=5[v0p];[v0p]concat=n=1:v=1[outv]",
            "map": ["[outv]", "0:a?"],
        },
        "global_options": ["-y"],
    }

    new_data_2 = {
        "input_files": [
            "https://drive.google.com/uc?export=download&id=1ATipDW3BKwtVGmC1hG6CKQ7wcsYYEvcS",
            "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/Sintel.mp4",
            # "https://drive.google.com/uc?export=download&id=1HCr_UfoclSMB48xux4lZZUkFny_WdNap",
        ],
        "output_file": "output.mp4",
        "options": {
            "c:v": "libx264",
            "crf": "28",
            "preset": "veryfast",
            "pix_fmt": "yuv420p",
            "map": "[outv]",
            "filter_complex": "[0:v]trim=duration=5,setpts=PTS-STARTPTS[trimmed_v0];[trimmed_v0]scale=w='if(gte(iw/ih,1080/1920),-2,1080)':h='if(gte(iw/ih,1080/1920),1920,-2)',setsar=1,crop=w=1080:h=1920:x='(iw-1080)/2':y='(ih-1920)/2',format=yuv420p,setsar=1[sc_v0];[sc_v0]drawtext=fontfile='/usr/share/fonts/custom/DejaVuSans.ttf':text='ugc agencies got you broke?':fontsize=35:fontcolor=white:x=(w-text_w)/2:y=h*0.15:box=1:boxcolor=black@0.6:boxborderw=5, drawtext=fontfile='/usr/share/fonts/custom/DejaVuSans.ttf':text='$6k a month for content? that'\\\\\\''s robbin'\\\\\\'' season.':fontsize=28:fontcolor=white:x=(w-text_w)/2:y=h*0.80:box=1:boxcolor=black@0.6:boxborderw=5[v0p];[1:v]trim=duration=5,setpts=PTS-STARTPTS[trimmed_v1];[trimmed_v1]scale=w='if(gte(iw/ih,1080/1920),-2,1080)':h='if(gte(iw/ih,1080/1920),1920,-2)',setsar=1,crop=w=1080:h=1920:x='(iw-1080)/2':y='(ih-1920)/2',format=yuv420p,setsar=1[sc_v1];[sc_v1]drawtext=fontfile='/usr/share/fonts/custom/DejaVuSans.ttf':text='doing it all yourself?':fontsize=35:fontcolor=white:x=(w-text_w)/2:y=h*0.15:box=1:boxcolor=black@0.6:boxborderw=5, drawtext=fontfile='/usr/share/fonts/custom/DejaVuSans.ttf':text='research\\\\, plan\\\\, film\\\\, edit\\\\, post... that'\\\\\\''s a full-time job (that you'\\\\\\''re not getting paid for).':fontsize=28:fontcolor=white:x=(w-text_w)/2:y=h*0.80:box=1:boxcolor=black@0.6:boxborderw=5[v1p];[v0p][v1p]concat=n=2:v=1[outv]",
        },
        "global_options": ["-y"],
    }

    new_data_3 = {
        "input_files": [
            "https://storage.charichagaming.com.np/video-storage/12779356_3840_2160_50fps.mp4",
            "https://storage.charichagaming.com.np/audio-storage/fb92aa39-4e6c-4a7d-80ef-49db76f10325.mp3",
        ],
        "output_file": str(time.time()) + ".mp4",
        "options": {
            "filter_complex": "[0:v:0]scale=1920:1080[v_final]",
            "map": ["[v_final]", "1:a:0"],
            "c:v": "libx264",
            "preset": "ultrafast",
            "crf": "25",
            "c:a": "libmp3lame",
            "q:a": "7",
            "shortest": True
        },
        "global_options": ["-y", "-stream_loop", "-1"],
    }


    # Send request to /compose endpoint
    print("Sending request to /compose endpoint...")
    response = requests.post(f"{BASE_URL}/compose", json=new_data_3)

    if response.status_code == 200:
        result = response.json()
        task_id = result.get("task_id")
        # Store the task ID in the global variable
        global current_task_id
        current_task_id = task_id
        print(f"Task submitted successfully. Task ID: {task_id}")

        # Poll for task status
        print("Polling for task status...")
        try:
            while True:
                status_response = requests.get(f"{BASE_URL}/tasks/{task_id}")
                status_data = status_response.json()

                print(f"Task status: {status_data.get('status')}")
                print(f"Progress: {status_data.get('progress')}")

                if status_data.get("status") in ["SUCCESS", "FAILURE", "REVOKED"]:
                    print("Task completed.")
                    print(json.dumps(status_data, indent=2))
                    # Clear the task ID as it's completed
                    current_task_id = None
                    break

                time.sleep(2)  # Wait for 2 seconds before polling again
        except KeyboardInterrupt:
            # This will be caught by the signal handler, but we add it here for clarity
            pass
    else:
        print(f"Error: {response.status_code}")
        print(response.text)


def main():
    print("FFmpeg Compose API Test")
    print("=======================")

    # Register signal handlers for graceful termination
    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Termination signal

    # Register cleanup function to be called on normal exit
    atexit.register(cleanup)

    # Check if API is running
    try:
        response = requests.get(f"{BASE_URL}/")
        if response.status_code == 200:
            print("API is running.")
            test_compose_endpoint()
        else:
            print(f"API returned unexpected status code: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to the API.")
        print("Make sure the API server is running at http://localhost:5200")
        sys.exit(1)


if __name__ == "__main__":
    main()
