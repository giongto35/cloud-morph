"""FastAPI server for Wine Environment"""

from fastapi import FastAPI, Body
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
import uvicorn
from typing import Dict, Any
import asyncio
from concurrent.futures import ThreadPoolExecutor
import base64
import numpy as np
import cv2
from io import BytesIO
from PIL import Image
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.wine_environment import WineEnvironment
from models import WineAction

# Singleton environment
_env = None

def get_env():
    global _env
    if _env is None:
        _env = WineEnvironment(
            screen_width=int(os.getenv("SCREEN_WIDTH", "800")),
            screen_height=int(os.getenv("SCREEN_HEIGHT", "600")),
        )
    return _env

executor = ThreadPoolExecutor(max_workers=1)
app = FastAPI(title="Wine Environment")


def encode_frame(frame: np.ndarray) -> str:
    """Encode frame to base64 JPEG"""
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    image = Image.fromarray(frame_rgb)
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("utf-8")


def serialize_observation(obs) -> Dict[str, Any]:
    """Serialize observation to JSON"""
    return {
        "observation": {
            "screen": encode_frame(obs.screen),
            "screen_shape": list(obs.screen_shape),
            "metadata": obs.metadata,
        },
        "reward": None,
        "done": False,
    }


@app.post("/reset")
async def reset(request: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    """Reset environment"""
    env = get_env()
    loop = asyncio.get_event_loop()
    obs = await loop.run_in_executor(executor, env.reset)
    return serialize_observation(obs)


@app.post("/step")
async def step(request: Dict[str, Any]) -> Dict[str, Any]:
    """Execute action"""
    env = get_env()
    action_data = request.get("action", request)
    action = WineAction(**action_data)
    
    loop = asyncio.get_event_loop()
    obs = await loop.run_in_executor(executor, env.step, action)
    return serialize_observation(obs)


@app.get("/state")
async def get_state() -> Dict[str, Any]:
    """Get environment state"""
    env = get_env()
    state = env.state
    return {
        "episode_id": state.episode_id,
        "step_count": state.step_count,
        "app_file": state.app_file,
        "window_title": state.window_title,
        "screen_width": state.screen_width,
        "screen_height": state.screen_height,
    }


@app.get("/health")
async def health() -> Dict[str, str]:
    """Health check"""
    return {"status": "healthy"}


@app.get("/stream")
async def stream_mjpeg():
    """MJPEG stream for real-time viewing"""
    async def generate():
        env = get_env()
        loop = asyncio.get_event_loop()
        while True:
            try:
                frame = await loop.run_in_executor(executor, env._capture_screen)
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(frame_rgb)
                buffer = BytesIO()
                image.save(buffer, format="JPEG", quality=85)
                buffer.seek(0)
                yield b'\r\n--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.read() + b'\r\n'
                await asyncio.sleep(0.1)
            except Exception as e:
                print(f"Stream error: {e}")
                await asyncio.sleep(0.5)
    
    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/viewer")
async def viewer():
    """HTML viewer page"""
    return HTMLResponse("""
<!DOCTYPE html>
<html>
<head>
    <title>Wine Environment</title>
    <style>
        body { margin: 0; padding: 20px; background: #1a1a1a; color: #fff; font-family: sans-serif; }
        .container { max-width: 1000px; margin: 0 auto; text-align: center; }
        h1 { margin-bottom: 20px; }
        img { border: 2px solid #333; max-width: 100%; }
        .info { margin-top: 20px; padding: 15px; background: #2a2a2a; border-radius: 8px; }
        .live { color: #4caf50; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🍷 Wine Environment</h1>
        <img src="/stream" alt="Stream" />
        <div class="info">
            <p>Status: <span class="live">● LIVE</span></p>
            <p>Stream: <code>http://localhost:8000/stream</code></p>
        </div>
    </div>
</body>
</html>
    """)


if __name__ == "__main__":
    # Create logs directory
    os.makedirs("/app/logs", exist_ok=True)
    
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    print(f"Starting server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)

