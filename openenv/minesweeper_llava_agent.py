#!/usr/bin/env python3
"""
Vision-assisted Minesweeper agent for OpenEnv.

Requires:
- OpenEnv container running Minesweeper (e.g., ./run_minesweeper.sh on port 8000)
- mlenv conda env with `ollama` Python client and a vision model (default: llava)

Behavior:
- Calls /reset to start a session and fetches base64 screen.
- Sends the screen to Ollama llava with a structured JSON prompt to identify cells.
- Chooses an unopened/unknown cell (least visited) and clicks via /step with normalized coords.
- Saves optional debug overlays and prints decisions.
"""

import argparse
import base64
import io
import json
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import ollama
import requests
from PIL import Image, ImageDraw

# #region agent log helper
DEBUG_LOG_PATH = "/home/giongto/code/cloud-morph/.cursor/debug.log"
SESSION_ID = "debug-session"
RUN_ID = "hang-investigation"


def dbg(hypothesis_id: str, location: str, message: str, data: dict):
    try:
        payload = {
            "sessionId": SESSION_ID,
            "runId": RUN_ID,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with open(DEBUG_LOG_PATH, "a") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass
# #endregion


def log(msg: str):
    print(msg, flush=True)


# ----------------------- Client helpers ----------------------- #


def _decode_frame(obs_json: dict) -> np.ndarray:
    """Decode base64 JPEG frame from OpenEnv observation into RGB numpy array."""
    b64 = obs_json["observation"]["screen"]
    raw = base64.b64decode(b64)
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    return np.array(img)


@dataclass
class Observation:
    image: np.ndarray  # RGB
    screen_shape: Tuple[int, int, int]
    metadata: dict


class OpenEnvClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

    def reset(self) -> Observation:
        r = self.session.post(f"{self.base_url}/reset", timeout=15)
        r.raise_for_status()
        payload = r.json()
        img = _decode_frame(payload)
        return Observation(img, tuple(img.shape), payload.get("observation", {}).get("metadata", {}))

    def step_click(self, x: float, y: float) -> Observation:
        """Send a mouse click at pixel coordinates."""
        payload = {
            "action_type": "mouse",
            "button": "left",
            "mouse_state": "click",
            "x": float(x),
            "y": float(y),
        }
        r = self.session.post(f"{self.base_url}/step", json=payload, timeout=15)
        r.raise_for_status()
        data = r.json()
        img = _decode_frame(data)
        return Observation(img, tuple(img.shape), data.get("observation", {}).get("metadata", {}))


# ----------------------- Vision parsing ----------------------- #


SYSTEM_PROMPT_BASE = """
This is minesweeper board screen 9 x 9. number means the number of bombs around the cell. light grey mean unopened cell. dark grey mean opened cell. black mean bomb. red mean exploded bomb. select the cell with highest probability of not being a bomb. Don't select the cell that is already opened or exploded.
Rules:
- Exclude UI outside the playable grid.
- Select the cell with highest probability of not being a bomb.

If there is red cell, or black cell appears multiple times, it means the bomb is exploded and game is over. is_game_over is true.

Return JSON ONLY with this schema:
{
  "row": <int>,
  "col": <int>,
  "is_game_over": <bool>
}"""

SYSTEM_PROMPT_HISTORY = """Prior chosen cells (avoid repeating): {history}.
Select a cell that is likely safe (not a bomb) and not already chosen.
Return ONLY the JSON object."""


def _image_to_jpeg_bytes(img: np.ndarray) -> bytes:
    pil = Image.fromarray(img)
    buf = io.BytesIO()
    pil.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def call_llava(img: np.ndarray, model: str, history: List[Tuple[int, int]], max_retries: int = 2) -> Optional[dict]:
    """Send image to Ollama vision model and parse JSON response."""
    jpeg_bytes = _image_to_jpeg_bytes(img)
    last_err: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        dbg("H1", "call_llava", "attempt", {"attempt": attempt})
        try:
            hist_str = "; ".join([f"({r},{c})" for r, c in history]) or "none"
            sys_prompt = SYSTEM_PROMPT_BASE + "\n" + SYSTEM_PROMPT_HISTORY.format(history=hist_str)
            resp = ollama.chat(
                model=model,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": "Select a safe unopened cell on the 9x9 Minesweeper board. If there is red cell, or black cell appears multiple times, it means the bomb is exploded and game is over. is_game_over is true.", "images": [jpeg_bytes]},
                ],
                format="json",
            )
            content = resp["message"]["content"]
            # Print raw response (truncated) for inspection
            raw_preview = content[:500].replace("\n", " ")
            print(f"[vision raw attempt {attempt}] {raw_preview}")
            try:
                parsed = json.loads(content)
            except Exception:
                # fallback: simple regex extract row/col
                import re
                m = re.search(r'"?row"?\s*[:=]\s*([0-9]+).*"col"?\s*[:=]\s*([0-9]+)', content, re.IGNORECASE | re.DOTALL)
                if m:
                    parsed = {"row": int(m.group(1)), "col": int(m.group(2)), "is_game_over": False}
                else:
                    raise
            dbg("H1", "call_llava", "success", {"attempt": attempt, "cells": len(parsed.get("cells", [])) if isinstance(parsed.get("cells"), list) else 0})
            return parsed
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(1.0)
    dbg("H1", "call_llava", "failed", {"error": str(last_err)})
    print(f"[vision] failed to parse LLM response: {last_err}")
    return None


# ----------------------- Move selection ----------------------- #


UNOPENED_STATES = {"unopened", "unknown", "covered"}
FIXED_ROWS = 9
FIXED_COLS = 9


@dataclass
class Cell:
    row: int
    col: int
    state: str
    x_norm: float
    y_norm: float


def _extract_cells(parsed: dict) -> Tuple[int, int, List[Cell]]:
    rows = FIXED_ROWS
    cols = FIXED_COLS
    cell_obj = parsed.get("cell") or parsed.get("cells")
    cells: List[Cell] = []

    # Accept top-level row/col
    if not cell_obj and "row" in parsed and "col" in parsed:
        cell_obj = parsed

    if isinstance(cell_obj, list) and cell_obj:
        cell_obj = cell_obj[0]
    if isinstance(cell_obj, dict):
        try:
            row = int(cell_obj.get("row", 0))
            col = int(cell_obj.get("col", 0))
            state = str(cell_obj.get("state", "unknown")).lower() if "state" in cell_obj else "unknown"
            x_norm = (float(cell_obj.get("center_norm", [0.0, 0.0])[0])
                      if isinstance(cell_obj.get("center_norm"), list) and len(cell_obj.get("center_norm")) == 2 else 0.0)
            y_norm = (float(cell_obj.get("center_norm", [0.0, 0.0])[1])
                      if isinstance(cell_obj.get("center_norm"), list) and len(cell_obj.get("center_norm")) == 2 else 0.0)
            cells.append(Cell(row=row, col=col, state=state, x_norm=x_norm, y_norm=y_norm))
        except Exception:
            pass
    is_game_over = bool(parsed.get("is_game_over", False))
    return rows, cols, cells, is_game_over


def pick_cell(rows: int, cols: int, cells: List[Cell], visits: Dict[Tuple[int, int], int]) -> Optional[Cell]:
    """Choose an unopened/unknown cell with the fewest visits."""
    unopened = [c for c in cells if c.state in UNOPENED_STATES]
    if not unopened:
        return None
    unopened.sort(key=lambda c: (visits.get((c.row, c.col), 0), c.row, c.col))
    return unopened[0]


def clamp01(v: float) -> float:
    return min(1.0, max(0.0, v))


def draw_debug(img: np.ndarray, cell: Cell, path: str):
    """Overlay chosen click and save."""
    h, w = img.shape[0], img.shape[1]
    x = (cell.x_norm * w) if cell.x_norm <= 1 else cell.x_norm
    y = (cell.y_norm * h) if cell.y_norm <= 1 else cell.y_norm
    pil = Image.fromarray(img)
    draw = ImageDraw.Draw(pil)
    draw.ellipse([x - 6, y - 6, x + 6, y + 6], outline=(255, 0, 0), width=3)
    draw.text((x + 8, y - 8), f"{cell.row},{cell.col}", fill=(255, 0, 0))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pil.save(path, format="JPEG")


# ----------------------- Main loop ----------------------- #


def run_agent(base_url: str, model: str, max_steps: int, debug_dir: Optional[str]):
    log(f"[init] base_url={base_url} model={model} max_steps={max_steps}")
    client = OpenEnvClient(base_url)
    log("[init] calling /reset")
    obs = client.reset()
    dbg("H3", "run_agent", "reset_done", {"shape": getattr(obs, "screen_shape", None)})
    img = obs.image
    visits: Dict[Tuple[int, int], int] = {}
    allow_gameover_check = True
    # Fixed board geometry (9x9): width=170px with 8px border each side; top offset 30px
    FIELD_X0, FIELD_Y0 = 8, 30 + 8  # start after left border and top border
    FIELD_W, FIELD_H = 170 - 16, 170 - 16  # usable grid area after removing borders
    CELL_W = FIELD_W / FIXED_COLS
    CELL_H = FIELD_H / FIXED_ROWS

    def prep_ui() -> np.ndarray:
        """Click dialog OK then center to bring board up."""
        log("[prep] clicking OK dialog")
        dbg("H5", "prep_ui", "click_ok", {})
        obs_local = client.step_click(FIELD_X0 + FIELD_W * 0.2, FIELD_Y0 + FIELD_H * 0.15)
        time.sleep(0.1)
        log("[prep] clicking center to start")
        dbg("H5", "prep_ui", "click_center", {})
        obs_local = client.step_click(FIELD_X0 + FIELD_W * 0.5, FIELD_Y0 + FIELD_H * 0.5)
        time.sleep(0.2)
        return obs_local.image

    # Focus the game window and clear dialog
    img = prep_ui()

    def clamp_edge(x: float, y: float, margin: float = 2.0) -> Tuple[float, float]:
        min_x = FIELD_X0 + margin
        max_x = FIELD_X0 + FIELD_W - margin
        min_y = FIELD_Y0 + margin
        max_y = FIELD_Y0 + FIELD_H - margin
        return min(max_x, max(min_x, x)), min(max_y, max(min_y, y))

    def to_field_pixels(cell: Cell, rows: int, cols: int) -> Tuple[float, float]:
        # Map row/col to pixel using fixed grid geometry
        r = cell.row if cell.row is not None else 0
        c = cell.col if cell.col is not None else 0
        x_pix = FIELD_X0 + (c + 0.5) * CELL_W
        y_pix = FIELD_Y0 + (r + 0.5) * CELL_H
        return clamp_edge(x_pix, y_pix, margin=2.0)

    def summarize_cells(cells: List[Cell]) -> Dict[str, int]:
        cnt: Dict[str, int] = {}
        for c in cells:
            cnt[c.state] = cnt.get(c.state, 0) + 1
        return cnt
    chosen_history: List[Tuple[int, int]] = []

    for step in range(1, max_steps + 1):
        log(f"[step {step}] start")
        log(f"[step {step}] calling llava")
        parsed = call_llava(img, model=model, history=chosen_history)
        cell: Optional[Cell] = None
        log(f"[step {step}] llava done {'ok' if parsed else 'None'}")
        dbg("H3", "run_agent", "llava_done", {"step": step, "parsed": bool(parsed)})

        if parsed:
            rows, cols, cells, is_game_over = _extract_cells(parsed)
            dbg("H7", "run_agent", "llava_cells", {"step": step, "rows": rows, "cols": cols, "counts": summarize_cells(cells), "is_game_over": is_game_over})
            print(f"[step {step}] llava cells: rows={rows} cols={cols} counts={summarize_cells(cells)} is_game_over={is_game_over}")
            if is_game_over:
                log(f"[step {step}] LLM marked game over; stopping.")
                dbg("H6", "run_agent", "game_over_llm", {"step": step})
                break
            if cells:
                cell = cells[0]

        if not cell:
            log(f"[step {step}] no cell from llava; stopping.")
            break

        # Convert to pixel coordinates on the field and clamp away from edges
        x_pix, y_pix = to_field_pixels(cell, FIXED_ROWS, FIXED_COLS)
        cell = Cell(row=cell.row, col=cell.col, state=cell.state, x_norm=x_pix, y_norm=y_pix)
        chosen_history.append((cell.row, cell.col))

        visits[(cell.row, cell.col)] = visits.get((cell.row, cell.col), 0) + 1
        # Send click
        log(f"[step {step}] clicking at ({cell.x_norm:.3f},{cell.y_norm:.3f}) state={cell.state}")
        dbg("H3", "run_agent", "click", {"step": step, "x": cell.x_norm, "y": cell.y_norm, "state": cell.state})
        obs = client.step_click(cell.x_norm, cell.y_norm)
        img = obs.image

        if debug_dir:
            out_path = os.path.join(debug_dir, f"step_{step:02d}.jpg")
            draw_debug(img, cell, out_path)
            print(f"[step {step}] saved debug overlay -> {out_path}")

        # allow UI to update; slightly longer wait helps ensure redraw
        time.sleep(0.6)
        log(f"[step {step}] done")
        dbg("H3", "run_agent", "step_done", {"step": step})


def parse_args():
    ap = argparse.ArgumentParser(description="Minesweeper Ollama vision agent for OpenEnv.")
    ap.add_argument("--base-url", default="http://localhost:8000", help="OpenEnv base URL")
    ap.add_argument("--model", default="llava", help="Ollama vision model to use")
    ap.add_argument("--max-steps", type=int, default=120, help="Maximum steps/clicks to perform")
    ap.add_argument("--debug-dir", default=None, help="Directory to save debug overlays (optional)")
    return ap.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_agent(
        base_url=args.base_url,
        model=args.model,
        max_steps=args.max_steps,
        debug_dir=args.debug_dir,
    )

