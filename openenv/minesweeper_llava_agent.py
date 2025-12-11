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

    def step_click(self, x_norm: float, y_norm: float) -> Observation:
        """Send a mouse click at normalized coordinates (0-1)."""
        payload = {
            "action_type": "mouse",
            "button": "left",
            "mouse_state": "click",
            "x": float(x_norm),
            "y": float(y_norm),
        }
        r = self.session.post(f"{self.base_url}/step", json=payload, timeout=15)
        r.raise_for_status()
        data = r.json()
        img = _decode_frame(data)
        return Observation(img, tuple(img.shape), data.get("observation", {}).get("metadata", {}))


# ----------------------- Vision parsing ----------------------- #


SYSTEM_PROMPT = """You are a precise Minesweeper vision parser. Return JSON ONLY.
Output schema (no extra text):
{
  "rows": <int>,
  "cols": <int>,
  "cells": [
    {"row": <int>, "col": <int>, "state": "<state>", "center_norm": [<x0-1>, <y0-1>]}
  ]
}
Rules:
- state must be one of: unopened, unknown, number0, number1, number2, number3, number4, number5, number6, number7, number8, mine, exploded, flagged, boundary.
- center_norm is normalized to full screenshot (0-1 floats).
- Include every playable cell in the grid.
- Use number0 for revealed empty cells.
- Exclude UI outside the playable grid.
Return ONLY the JSON object."""


def _image_to_jpeg_bytes(img: np.ndarray) -> bytes:
    pil = Image.fromarray(img)
    buf = io.BytesIO()
    pil.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def call_llava(img: np.ndarray, model: str, max_retries: int = 2) -> Optional[dict]:
    """Send image to Ollama vision model and parse JSON response."""
    jpeg_bytes = _image_to_jpeg_bytes(img)
    last_err: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        dbg("H1", "call_llava", "attempt", {"attempt": attempt})
        try:
            resp = ollama.chat(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": "Identify the Minesweeper board.", "images": [jpeg_bytes]},
                ],
                format="json",
            )
            content = resp["message"]["content"]
            parsed = json.loads(content)
            if "cells" not in parsed:
                raise ValueError("Missing 'cells' in LLM response")
            dbg("H1", "call_llava", "success", {"attempt": attempt, "cells": len(parsed.get("cells", []))})
            return parsed
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(1.0)
    dbg("H1", "call_llava", "failed", {"error": str(last_err)})
    print(f"[vision] failed to parse LLM response: {last_err}")
    return None


# ----------------------- Move selection ----------------------- #


UNOPENED_STATES = {"unopened", "unknown", "covered"}


@dataclass
class Cell:
    row: int
    col: int
    state: str
    x_norm: float
    y_norm: float


def _extract_cells(parsed: dict) -> Tuple[int, int, List[Cell]]:
    # Attempt to use rows/cols from parsed
    rows = int(parsed.get("rows", 0) or 0)
    cols = int(parsed.get("cols", 0) or 0)
    cells_raw = parsed.get("cells", []) or []
    cells: List[Cell] = []

    # Helper to map numeric grid values to states
    def num_to_state(val) -> str:
        try:
            iv = int(val)
            if iv < 0:
                return "unopened"
            if iv == 0:
                return "number0"
            if 1 <= iv <= 8:
                return f"number{iv}"
            return "unknown"
        except Exception:
            return "unknown"

    # First pass: parse provided cells
    for c in cells_raw:
        try:
            row = int(c.get("row", 0))
            col = int(c.get("col", 0))
            state = str(c.get("state", "unknown")).lower()
            center = c.get("center_norm") or c.get("center") or c.get("centerNormalized")
            if center and len(center) == 2:
                x_norm = float(center[0])
                y_norm = float(center[1])
            else:
                bbox = c.get("bbox_norm") or c.get("bbox")
                if bbox and len(bbox) == 4:
                    x0, y0, x1, y1 = bbox
                    x_norm = (float(x0) + float(x1)) / 2
                    y_norm = (float(y0) + float(y1)) / 2
                else:
                    # If we know rows/cols we can synthesize a center
                    if rows > 0 and cols > 0:
                        x_norm = (col + 0.5) / cols
                        y_norm = (row + 0.5) / rows
                    else:
                        continue
            cells.append(Cell(row=row, col=col, state=state, x_norm=x_norm, y_norm=y_norm))
            rows = max(rows, row + 1)
            cols = max(cols, col + 1)
        except Exception:
            continue

    # Fallback: if no usable cells, try to derive from a "grid" matrix
    if not cells and isinstance(parsed.get("grid"), list):
        grid = parsed["grid"]
        rows = len(grid)
        cols = len(grid[0]) if grid and isinstance(grid[0], list) else cols
        for r, row_vals in enumerate(grid):
            for c_idx, val in enumerate(row_vals if isinstance(row_vals, list) else []):
                state = num_to_state(val)
                x_norm = (c_idx + 0.5) / max(cols, 1)
                y_norm = (r + 0.5) / max(rows, 1)
                cells.append(Cell(row=r, col=c_idx, state=state, x_norm=x_norm, y_norm=y_norm))

    return rows, cols, cells


def pick_cell(rows: int, cols: int, cells: List[Cell], visits: Dict[Tuple[int, int], int]) -> Optional[Cell]:
    """Choose an unopened/unknown cell with the fewest visits."""
    unopened = [c for c in cells if c.state in UNOPENED_STATES]
    if not unopened:
        return None
    unopened.sort(key=lambda c: (visits.get((c.row, c.col), 0), c.row, c.col))
    return unopened[0]


# ----------------------- Pixel-based fallback ----------------------- #


def find_grid_edges(img: np.ndarray, axis: int, thresh_scale: float = 2.0) -> List[int]:
    diff = np.abs(np.diff(img.astype(np.int16), axis=axis)).mean(
        axis=tuple(i for i in range(img.ndim) if i != axis)
    )
    strength = diff
    mean, std = strength.mean(), strength.std()
    thresh = mean + thresh_scale * std
    peaks = np.where(strength > thresh)[0]
    return peaks.tolist()


def mode_diff(peaks: List[int]) -> Optional[int]:
    if len(peaks) < 2:
        return None
    diffs = [b - a for a, b in zip(peaks, peaks[1:]) if b - a > 2]
    if not diffs:
        return None
    cnt = Counter(diffs)
    return cnt.most_common(1)[0][0]


def infer_grid(img: np.ndarray) -> Tuple[int, int, int, int, int, int]:
    mask = (img.sum(axis=2) > 50)
    ys, xs = np.where(mask)
    y0i, y1i = ys.min(), ys.max()
    x0i, x1i = xs.min(), xs.max()
    sub = img[y0i:y1i + 1, x0i:x1i + 1]

    peaks_y = find_grid_edges(sub, axis=0)
    peaks_x = find_grid_edges(sub, axis=1)

    cell_h = mode_diff(peaks_y) or 14
    cell_w = mode_diff(peaks_x) or 12

    y0 = (peaks_y[0] if peaks_y else 18) + y0i
    x0 = (peaks_x[0] if peaks_x else 2) + x0i

    max_rows = (img.shape[0] - y0) // cell_h
    max_cols = (img.shape[1] - x0) // cell_w
    rows = min(max_rows, 16)
    cols = min(max_cols, 16)
    return x0, y0, cell_w, cell_h, cols, rows


def classify_cell(patch: np.ndarray) -> str:
    mean_val = float(patch.mean())
    std_val = float(patch.std())
    colors = patch.reshape(-1, 3)
    cnt = Counter(map(tuple, colors))
    (r, g, b), _ = cnt.most_common(1)[0]

    if mean_val > 220 and std_val < 35:
        return "open"
    if mean_val < 95 and std_val < 40:
        return "unopened"
    if 110 <= mean_val <= 190 and std_val < 32:
        return "unopened"
    if std_val < 10 and mean_val > 200:
        return "open"

    def dominant(c1, c2, c3, margin):
        return c1 > c2 + margin and c1 > c3 + margin

    if dominant(b, r, g, 30):
        return "number1"
    if dominant(g, r, b, 20):
        return "number2"
    if dominant(r, g, b, 20):
        return "number3"
    if dominant(b, r, g, 10) and b > 100:
        return "number4"
    if dominant(r, g, b, 10) and g < 80 and b < 80:
        return "number5"
    if dominant(g, b, r, 10) and r < 80:
        return "number6"

    return "unopened"


@dataclass
class Board:
    x0: int
    y0: int
    cw: int
    ch: int
    cols: int
    rows: int
    grid: List[List[str]]

    @classmethod
    def from_image(cls, img, x0, y0, cw, ch, cols, rows):
        grid = []
        for r in range(rows):
            row = []
            for c in range(cols):
                y_start = y0 + r * ch
                x_start = x0 + c * cw
                patch = img[y_start:y_start + ch, x_start:x_start + cw]
                row.append(classify_cell(patch))
            grid.append(row)
        return cls(x0, y0, cw, ch, cols, rows, grid)

    def neighbors(self, r, c):
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                rr, cc = r + dr, c + dc
                if 0 <= rr < self.rows and 0 <= cc < self.cols:
                    yield rr, cc

    def deduce(self) -> Tuple[set, set]:
        safe = set()
        mines = set()
        flagged = set()

        def num(val):
            if val.startswith("number"):
                try:
                    return int(val.replace("number", ""))
                except ValueError:
                    return None
            return None

        for r in range(self.rows):
            for c in range(self.cols):
                n = num(self.grid[r][c])
                if n is None:
                    continue
                neigh = list(self.neighbors(r, c))
                unopened = [(rr, cc) for rr, cc in neigh if self.grid[rr][cc] == "unopened"]
                flagged_count = len([1 for rr, cc in neigh if (rr, cc) in flagged])
                if not unopened:
                    continue
                if n == len(unopened) + flagged_count:
                    for cell in unopened:
                        mines.add(cell)
                        flagged.add(cell)
                if flagged_count == n:
                    for cell in unopened:
                        if cell not in mines:
                            safe.add(cell)
        return safe, mines


def pixel_fallback_cells(img: np.ndarray) -> Tuple[int, int, List[Cell], Optional[Board]]:
    try:
        x0, y0, cw, ch, cols, rows = infer_grid(img)
        board = Board.from_image(img, x0, y0, cw, ch, cols, rows)
        cells: List[Cell] = []
        dbg("H2", "pixel_fallback_cells", "grid", {"x0": x0, "y0": y0, "cw": cw, "ch": ch, "cols": cols, "rows": rows})
        for r in range(rows):
            for c in range(cols):
                state = board.grid[r][c]
                x_center = x0 + c * cw + cw / 2
                y_center = y0 + r * ch + ch / 2
                cells.append(
                    Cell(
                        row=r,
                        col=c,
                        state=state,
                        x_norm=x_center / img.shape[1],
                        y_norm=y_center / img.shape[0],
                    )
                )
        return rows, cols, cells, board
    except Exception:
        dbg("H2", "pixel_fallback_cells", "error", {})
        return 0, 0, [], None


def clamp01(v: float) -> float:
    return min(1.0, max(0.0, v))


def draw_debug(img: np.ndarray, cell: Cell, path: str):
    """Overlay chosen click and save."""
    h, w = img.shape[0], img.shape[1]
    x = clamp01(cell.x_norm) * w
    y = clamp01(cell.y_norm) * h
    pil = Image.fromarray(img)
    draw = ImageDraw.Draw(pil)
    draw.ellipse([x - 6, y - 6, x + 6, y + 6], outline=(255, 0, 0), width=3)
    draw.text((x + 8, y - 8), f"{cell.row},{cell.col}", fill=(255, 0, 0))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pil.save(path, format="JPEG")


def detect_bomb(img: np.ndarray, red_thresh: int = 180, green_thresh: int = 80, blue_thresh: int = 80, min_pixels: int = 120):
    """Heuristic bomb detection: look for red-dominant pixels typical of explosion."""
    if img is None or img.size == 0:
        return False
    r = img[:, :, 0]
    g = img[:, :, 1]
    b = img[:, :, 2]
    mask = (r > red_thresh) & (g < green_thresh) & (b < blue_thresh)
    count = int(mask.sum())
    dbg("H4", "detect_bomb", "bomb_pixels", {"count": count})
    return count >= min_pixels


# ----------------------- Main loop ----------------------- #


def run_agent(base_url: str, model: str, max_steps: int, debug_dir: Optional[str]):
    log(f"[init] base_url={base_url} model={model} max_steps={max_steps}")
    client = OpenEnvClient(base_url)
    log("[init] calling /reset")
    obs = client.reset()
    dbg("H3", "run_agent", "reset_done", {"shape": getattr(obs, "screen_shape", None)})
    img = obs.image
    visits: Dict[Tuple[int, int], int] = {}
    last_board: Optional[Board] = None
    sweep_idx = 0
    first_click_done = False

    def prep_ui() -> np.ndarray:
        """Click dialog OK then center to bring board up."""
        log("[prep] clicking OK dialog")
        dbg("H5", "prep_ui", "click_ok", {})
        obs_local = client.step_click(0.2, 0.15)
        time.sleep(0.1)
        log("[prep] clicking center to start")
        dbg("H5", "prep_ui", "click_center", {})
        obs_local = client.step_click(0.5, 0.5)
        time.sleep(0.2)
        return obs_local.image

    # Focus the game window and clear dialog
    img = prep_ui()

    def clamp_edge(x: float, y: float, edge: float = 0.1) -> Tuple[float, float]:
        return clamp01(max(edge, min(1 - edge, x))), clamp01(max(edge, min(1 - edge, y)))

    for step in range(1, max_steps + 1):
        log(f"[step {step}] start")
        log(f"[step {step}] calling llava")
        parsed = call_llava(img, model=model)
        cell: Optional[Cell] = None
        board: Optional[Board] = None
        log(f"[step {step}] llava done {'ok' if parsed else 'None'}")
        dbg("H3", "run_agent", "llava_done", {"step": step, "parsed": bool(parsed)})

        if parsed:
            rows, cols, cells = _extract_cells(parsed)
            if cells:
                cell = pick_cell(rows, cols, cells, visits)
                if cell:
                    print(f"[step {step}] clicking cell r={cell.row} c={cell.col} state={cell.state} at ({cell.x_norm:.3f},{cell.y_norm:.3f})")

        # Pixel fallback if LLM gave nothing
        if not cell:
            rows_fb, cols_fb, cells_fb, board = pixel_fallback_cells(img)
            if board:
                safe, _ = board.deduce()
                safe_cells = [c for c in cells_fb if (c.row, c.col) in safe and c.state == "unopened"]
                if safe_cells:
                    cell = sorted(safe_cells, key=lambda c: (visits.get((c.row, c.col), 0), c.row, c.col))[0]
                last_board = board
            if not cell and cells_fb:
                cell = pick_cell(rows_fb, cols_fb, cells_fb, visits)

        if not cell:
            log(f"[step {step}] no cell from llava/pixel; sweeping")
            # Deterministic sweep within last known board; fallback to full grid
            grid_n = last_board.cols if last_board else 16
            rows_n = last_board.rows if last_board else 16
            attempts = 0
            while attempts < grid_n * rows_n:
                r = sweep_idx // grid_n
                c = sweep_idx % grid_n
                sweep_idx = (sweep_idx + 1) % (grid_n * rows_n)
                attempts += 1
                if last_board:
                    x = last_board.x0 + c * last_board.cw + last_board.cw / 2
                    y = last_board.y0 + r * last_board.ch + last_board.ch / 2
                    coord = (x / img.shape[1], y / img.shape[0])
                else:
                    coord = (c + 0.5) / grid_n, (r + 0.5) / rows_n
                if visits.get((r, c), 0) < 2:
                    cell = Cell(row=r, col=c, state="sweep", x_norm=coord[0], y_norm=coord[1])
                    break
            if not cell:
                cell = Cell(row=-1, col=-1, state="fallback", x_norm=0.5, y_norm=0.5)
            print(f"[step {step}] sweep/fallback click at ({cell.x_norm:.3f},{cell.y_norm:.3f}) state={cell.state}")

        # Force safer opening: first click always center
        if not first_click_done:
            cell = Cell(row=-1, col=-1, state="center_open", x_norm=0.5, y_norm=0.5)
            first_click_done = True

        # Clamp away from edges to reduce corner bombs
        cell_x, cell_y = clamp_edge(cell.x_norm, cell.y_norm, edge=0.1)
        cell = Cell(row=cell.row, col=cell.col, state=cell.state, x_norm=cell_x, y_norm=cell_y)

        visits[(cell.row, cell.col)] = visits.get((cell.row, cell.col), 0) + 1
        # Send click
        log(f"[step {step}] clicking at ({cell.x_norm:.3f},{cell.y_norm:.3f}) state={cell.state}")
        dbg("H3", "run_agent", "click", {"step": step, "x": cell.x_norm, "y": cell.y_norm, "state": cell.state})
        obs = client.step_click(clamp01(cell.x_norm), clamp01(cell.y_norm))
        img = obs.image

        # Bomb detection: only log, do not reset
        if detect_bomb(img):
            log(f"[step {step}] bomb detected; continuing without reset")
            dbg("H4", "run_agent", "bomb_detected", {"step": step})

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

