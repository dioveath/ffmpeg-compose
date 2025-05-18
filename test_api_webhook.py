import requests
import json
import time
import sys
import signal
import atexit
import threading
import http.server
import socketserver

# API endpoint
BASE_URL = "http://localhost:5200"
WEBHOOK_PORT = 8120
WEBHOOK_URL = f"http://host.docker.internal:{WEBHOOK_PORT}/webhook"

# Global variable to store the current task ID
current_task_id = None
httpd = None

class WebhookHandler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        print("\nWebhook received:")
        try:
            print(json.dumps(json.loads(post_data.decode('utf-8')), indent=2))
        except json.JSONDecodeError:
            print(post_data.decode('utf-8'))
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        # Suppress a lot of the default logging to keep test output clean
        if "code 200" not in args[0] and "code 404" not in args[0]:
            super().log_message(format, *args)

def start_webhook_server():
    global httpd
    try:
        httpd = socketserver.TCPServer(("", WEBHOOK_PORT), WebhookHandler)
        print(f"Starting webhook server on port {WEBHOOK_PORT}...")
        httpd.serve_forever()
    except OSError as e:
        print(f"Error starting webhook server: {e}. Port {WEBHOOK_PORT} might be in use.")
        # If server fails to start, we should exit or handle appropriately
        # For this test script, we'll let the main script continue and likely fail at API call
        httpd = None # Ensure httpd is None if server didn't start

def stop_webhook_server():
    global httpd
    if httpd:
        print("\nStopping webhook server...")
        httpd.shutdown()
        httpd.server_close()
        print("Webhook server stopped.")

def cleanup():
    """Cleanup function to stop any running FFmpeg task and webhook server"""
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
    stop_webhook_server()

def signal_handler(sig, frame):
    """Handle termination signals"""
    print("\nReceived termination signal. Cleaning up...")
    cleanup()
    sys.exit(0)

def test_compose_endpoint_with_webhook():
    """Test the /compose endpoint with a webhook URL"""
    # Sample request data
    W = 1080
    H = 1920
    data = {
        "input_files": [
            "https://drive.google.com/uc?export=download&id=1ATipDW3BKwtVGmC1hG6CKQ7wcsYYEvcS"
        ],
        "output_file": "test_webhook.mp4",
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
        "webhook_url": WEBHOOK_URL
    }

    # Send request to /compose endpoint
    print("Sending request to /compose endpoint with webhook...")
    response = requests.post(f"{BASE_URL}/compose", json=data)

    global current_task_id
    if response.status_code == 200:
        result = response.json()
        task_id = result.get("task_id")
        current_task_id = task_id
        print(f"Task submitted successfully. Task ID: {task_id}")

        # Poll for task status (optional, as webhook should notify)
        # For this test, we'll still poll to see the task complete and then wait for webhook
        print("Polling for task status (webhook will also be called)...")
        try:
            while True:
                status_response = requests.get(f"{BASE_URL}/tasks/{task_id}")
                status_data = status_response.json()

                print(f"Task status: {status_data.get('status')}")
                print(f"Progress: {status_data.get('progress')}")

                if status_data.get("status") in ["SUCCESS", "FAILURE", "REVOKED"]:
                    print("Task completed based on polling.")
                    print(json.dumps(status_data, indent=2))
                    current_task_id = None # Clear task ID as it's completed
                    print("Waiting a bit for webhook to be called if not already...")
                    time.sleep(5) # Give some time for webhook to arrive
                    break
                time.sleep(2)
        except KeyboardInterrupt:
            pass # Will be caught by signal_handler
    else:
        print(f"Error: {response.status_code}")
        print(response.text)
        current_task_id = None

def main():
    print("FFmpeg Compose API Webhook Test")
    print("===============================")

    # Register signal handlers for graceful termination
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Register cleanup function to be called on normal exit
    atexit.register(cleanup)

    # Start webhook server in a separate thread
    webhook_thread = threading.Thread(target=start_webhook_server, daemon=True)
    webhook_thread.start()
    
    # Give the server a moment to start
    time.sleep(1)
    
    global httpd
    if not httpd and webhook_thread.is_alive(): # Check if server thread is alive but httpd is not set (e.g. port in use)
        print("Webhook server failed to start. Exiting.")
        # Attempt to stop the thread if it's stuck in serve_forever without httpd being set
        # This scenario is less likely with daemon=True but good to be cautious.
        # A more robust solution would involve inter-thread communication or checking httpd status.
        return
    elif not webhook_thread.is_alive():
        print("Webhook server thread did not start. Exiting.")
        return

    # Check if API is running
    try:
        response = requests.get(f"{BASE_URL}")
        if response.status_code == 200:
            print("API is running.")
            test_compose_endpoint_with_webhook()
        else:
            print(f"API returned unexpected status code: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to the API.")
        print(f"Make sure the API server is running at {BASE_URL}")
    finally:
        # Ensure cleanup is called, especially if main loop finishes before signals
        # atexit should handle this, but an explicit call here can be a safeguard
        # However, calling cleanup() here might be premature if tasks are still running
        # and rely on polling. The atexit and signal handlers are better.
        pass

if __name__ == "__main__":
    main()