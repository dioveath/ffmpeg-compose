import requests
import json
import time
import sys

# API endpoint
BASE_URL = "http://localhost:8000"

def test_compose_endpoint():
    """Test the /compose endpoint with a sample FFmpeg command"""
    # Sample request data
    W = 1080
    H = 1920
    data = {
        "input_files": ["input.mp4"],
        "output_file": "output.mp4",
        "options": {
            "filter_complex": f"[0:v]scale=w='if(gte(iw/ih,{W}/{H}), -2, {W})':h='if(gte(iw/ih,{W}/{H}), {H}, -2)',setsar=1[scaled_cover];" +
            f"[scaled_cover]crop=w={W}:h={H}:x='(iw-{W})/2':y='(ih-{H})/2',setsar=1[cropped_video]",
            "map": ["[cropped_video]", "0:a?"],
            "c:v": "libx264",
            "crf": 23,
            "preset": "medium",
            "c:a": "aac",
            "b:a": "128k"
        },
        "global_options": ["-y", "-v", "warning"]
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
            "map": ["[outv]","0:a?"]
        },
        "global_options": [
            "-y",
            "-v",
            "warning"
        ]
    }
    
    # Send request to /compose endpoint
    print("Sending request to /compose endpoint...")
    response = requests.post(f"{BASE_URL}/compose", json=new_data)
    
    if response.status_code == 200:
        result = response.json()
        task_id = result.get("task_id")
        print(f"Task submitted successfully. Task ID: {task_id}")
        
        # Poll for task status
        print("Polling for task status...")
        while True:
            status_response = requests.get(f"{BASE_URL}/tasks/{task_id}")
            status_data = status_response.json()
            
            print(f"Task status: {status_data.get('status')}")
            
            if status_data.get('status') in ['SUCCESS', 'FAILURE']:
                print("Task completed.")
                print(json.dumps(status_data, indent=2))
                break
                
            time.sleep(2)  # Wait for 2 seconds before polling again
    else:
        print(f"Error: {response.status_code}")
        print(response.text)

def main():
    print("FFmpeg Compose API Test")
    print("=======================")
    
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
        print("Make sure the API server is running at http://localhost:8000")
        sys.exit(1)

if __name__ == "__main__":
    main()