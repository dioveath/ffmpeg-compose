# FFmpeg Compose API

A FastAPI application that provides an API endpoint for processing FFmpeg commands with asynchronous task handling using Celery.

## Features

- `/compose` endpoint that accepts FFmpeg command options
- Asynchronous processing with Celery
- Task status tracking
- Pydantic validation for request data

## Requirements

- Python 3.8+
- FFmpeg installed and available in PATH
- Redis server (for Celery broker and backend)

## Installation

1. Clone the repository
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Make sure Redis is running on localhost:6379

## Running the Application

1. Start the FastAPI server:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

2. Start the Celery worker:

```bash
celery -A celery_worker worker --loglevel=info
```

3. (Optional) Start Flower for monitoring Celery tasks:

```bash
celery -A celery_worker flower --port=5555
```

## API Usage

### Compose FFmpeg Command

**Endpoint**: `POST /compose`

**Request Body**:

```json
{
  "input_files": ["path/to/input1.mp4", "path/to/input2.mp4"],
  "output_file": "path/to/output.mp4",
  "options": {
    "c:v": "libx264",
    "crf": 23,
    "preset": "medium"
  },
  "global_options": ["-y", "-v", "warning"]
}
```

**Response**:

```json
{
  "task_id": "task-uuid",
  "status": "Processing"
}
```

### Check Task Status

**Endpoint**: `GET /tasks/{task_id}`

**Response**:

```json
{
  "task_id": "task-uuid",
  "status": "SUCCESS",
  "result": {
    "success": true,
    "output_file": "path/to/output.mp4",
    "command": "ffmpeg -y -v warning -i path/to/input1.mp4 -i path/to/input2.mp4 -c:v libx264 -crf 23 -preset medium path/to/output.mp4",
    "message": "FFmpeg processing completed successfully"
  }
}
```

## Example Use Cases

1. **Video Transcoding**:
   - Convert video format (e.g., MP4 to WebM)
   - Change video codec (e.g., H.264 to H.265)

2. **Video Editing**:
   - Trim video segments
   - Concatenate multiple videos
   - Add watermarks or overlays

3. **Audio Processing**:
   - Extract audio from video
   - Change audio codec or bitrate
   - Mix multiple audio tracks

## License

MIT