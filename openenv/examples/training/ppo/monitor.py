#!/usr/bin/env python3
"""Real-time monitoring server for PPO training dashboard.

Two modes:
  1. LIVE  — Reads real data from PVC/K8s when training is running
  2. DEMO  — Runs a real CNN on procedural StarCraft frames, simulates
             Kueue worker lifecycle, and generates converging PPO metrics.
             Auto-activates when no real training data is detected.

Run:
    DATA_DIR=./data python monitor.py
    open http://localhost:9000
"""

import asyncio
import base64
import json
import math
import os
import random
import struct
import subprocess
import threading
import time
from pathlib import Path

import requests as http_requests

import cv2
import numpy as np
import torch
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from ppo import CNNAgent, compute_gae, ppo_update

# Action definitions — safe keys only (no Escape/Return which exit game)
KEY_ACTIONS = [
    {"action_type": "key", "key": k}
    for k in ["s", "b", "m", "p", "a", "h", "t", "g", "d", "r"]
]
MOUSE_ACTIONS = [
    {"action_type": "mouse", "x": int(64 + col * 128), "y": int(48 + row * 96),
     "button": "left", "mouse_state": "click"}
    for row in range(5) for col in range(5)
]
ALL_ACTIONS = KEY_ACTIONS + MOUSE_ACTIONS

app = FastAPI(title="PPO Training Monitor")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

DATA_DIR = os.environ.get("DATA_DIR", "/data")
NAMESPACE = os.environ.get("NAMESPACE", "openenv-training")
WORKER_URLS = os.environ.get("WORKER_URLS", "http://localhost:8000").split(",")
DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), "dashboard.html")

# ═══════════════════════════════════════════════════════════════════
# PROCEDURAL STARCRAFT RENDERER (640×480 → 84×84)
# ═══════════════════════════════════════════════════════════════════

class StarCraftRenderer:
    """Generates procedural StarCraft-like frames at 640×480.

    Renders a top-down RTS view with:
    - Dirt/grass terrain with creep, cliffs, ramps
    - Blue mineral crystals and green vespene geysers
    - Terran buildings (Command Center, Supply Depot, Barracks, etc.)
    - Units (SCVs mining, marines patrolling) with selection circles
    - StarCraft-style HUD: minimap (bottom-left), command card (bottom-right),
      info panel (bottom-center), resource bar (top)
    """

    # Game area is 640 × 375 (top portion), HUD is 640 × 105 (bottom)
    GAME_H = 375
    HUD_Y = 375
    HUD_H = 105

    def __init__(self):
        self.frame_count = 0
        self.minerals = 50
        self.gas = 0
        self.supply = 5
        self.supply_max = 10
        self.units = []
        self.buildings = []
        self.mineral_patches = []
        self.geysers = []
        self.terrain = None
        self.selected_unit = 0  # which unit is "selected"
        self._init_map()

    def _init_map(self):
        # Generate terrain — dark earthy tones with variation (vectorized)
        self.terrain = np.zeros((480, 640, 3), dtype=np.uint8)

        rng = np.random.RandomState(42)
        noise1 = rng.rand(480, 640).astype(np.float32)

        # Vectorized sine noise
        Y, X = np.mgrid[:480, :640].astype(np.float32)
        noise2 = (np.sin(X * 0.012 + 0.5) * np.cos(Y * 0.009)
                  + np.sin(X * 0.03 + Y * 0.02) * 0.4
                  + np.sin(X * 0.007 - Y * 0.005) * 0.6)

        n = noise2[:self.GAME_H] * 0.5 + noise1[:self.GAME_H] * 0.15
        r = np.clip(38 + n * 30 + noise1[:self.GAME_H] * 12, 20, 80).astype(np.uint8)
        g = np.clip(50 + n * 35 + noise1[:self.GAME_H] * 10, 28, 95).astype(np.uint8)
        b = np.clip(22 + n * 15 + noise1[:self.GAME_H] * 8, 10, 50).astype(np.uint8)
        self.terrain[:self.GAME_H, :, 0] = r
        self.terrain[:self.GAME_H, :, 1] = g
        self.terrain[:self.GAME_H, :, 2] = b

        # Darker cliff patches (vectorized per-patch)
        for _ in range(6):
            cx, cy = rng.randint(40, 600), rng.randint(40, 340)
            radius = rng.randint(25, 70)
            y0, y1 = max(0, cy - radius), min(self.GAME_H, cy + radius)
            x0, x1 = max(0, cx - radius), min(640, cx + radius)
            yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
            dist = np.sqrt((xx - cx)**2 + (yy - cy)**2)
            mask = dist < radius
            factor = np.where(mask, 0.65 + 0.35 * (dist / radius), 1.0).astype(np.float32)
            patch = self.terrain[y0:y1, x0:x1].astype(np.float32)
            for c in range(3):
                patch[:, :, c] *= factor
            self.terrain[y0:y1, x0:x1] = patch.astype(np.uint8)

        # Light grass patches (vectorized per-patch)
        for _ in range(8):
            cx, cy = rng.randint(20, 620), rng.randint(20, 355)
            radius = rng.randint(15, 45)
            y0, y1 = max(0, cy - radius), min(self.GAME_H, cy + radius)
            x0, x1 = max(0, cx - radius), min(640, cx + radius)
            yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
            dist = np.sqrt((xx - cx)**2 + (yy - cy)**2)
            blend = np.clip(1 - dist / radius, 0, 1) * 0.3 * 40
            patch_g = self.terrain[y0:y1, x0:x1, 1].astype(np.float32)
            self.terrain[y0:y1, x0:x1, 1] = np.clip(patch_g + blend, 0, 255).astype(np.uint8)

        # HUD background: solid dark gray (StarCraft console)
        self.terrain[self.HUD_Y:, :] = [18, 20, 24]

        # Mineral patches (clustered near top-right and mid-left)
        base_positions = [(100, 160), (480, 100)]
        for bx, by in base_positions:
            for i in range(6):
                angle = i * math.pi / 3 + random.uniform(-0.3, 0.3)
                dist = random.randint(15, 50)
                self.mineral_patches.append({
                    "x": bx + int(dist * math.cos(angle)),
                    "y": by + int(dist * math.sin(angle)),
                    "size": random.randint(9, 15),
                    "amount": random.randint(800, 1500),
                })

        # Vespene geysers
        self.geysers = [
            {"x": 170, "y": 120, "size": 16},
            {"x": 530, "y": 150, "size": 16},
        ]

        # Starting buildings (Terran, near bottom-center of game area)
        self.buildings = [
            {"x": 280, "y": 260, "w": 64, "h": 48, "type": "cc",
             "color": (85, 105, 135), "shadow": (40, 50, 65), "label": "Command Center", "hp": 1.0},
            {"x": 360, "y": 270, "w": 40, "h": 32, "type": "depot",
             "color": (75, 95, 120), "shadow": (35, 45, 60), "label": "Supply Depot", "hp": 1.0},
            {"x": 360, "y": 310, "w": 40, "h": 32, "type": "depot",
             "color": (75, 95, 120), "shadow": (35, 45, 60), "label": "Supply Depot", "hp": 1.0},
            {"x": 200, "y": 290, "w": 52, "h": 40, "type": "rax",
             "color": (80, 100, 130), "shadow": (38, 48, 63), "label": "Barracks", "hp": 1.0},
        ]

        # Starting units
        for i in range(4):
            self.units.append({
                "x": float(100 + random.randint(-20, 40)),
                "y": float(160 + random.randint(-20, 30)),
                "vx": random.uniform(-0.3, 0.3), "vy": random.uniform(-0.3, 0.3),
                "type": "scv", "color": (200, 200, 100), "size": 5, "hp": 1.0,
                "mining": True,
            })
        for i in range(4):
            self.units.append({
                "x": float(250 + random.randint(-30, 60)),
                "y": float(230 + random.randint(-20, 30)),
                "vx": random.uniform(-0.3, 0.3), "vy": random.uniform(-0.3, 0.3),
                "type": "marine", "color": (120, 170, 230), "size": 5, "hp": 1.0,
                "mining": False,
            })

    def step(self, action_idx: int) -> np.ndarray:
        """Advance simulation one step, return 640×480 RGB frame."""
        self.frame_count += 1
        t = self.frame_count

        # Move units
        for u in self.units:
            if u.get("mining") and u["type"] == "scv":
                # SCVs wander near mineral patches
                target = self.mineral_patches[hash(id(u)) % len(self.mineral_patches)]
                dx = target["x"] - u["x"]
                dy = target["y"] - u["y"]
                dist = max(1, math.sqrt(dx*dx + dy*dy))
                if dist > 8:
                    u["vx"] = dx / dist * 0.5 + random.uniform(-0.1, 0.1)
                    u["vy"] = dy / dist * 0.5 + random.uniform(-0.1, 0.1)
                else:
                    u["vx"] = random.uniform(-0.2, 0.2)
                    u["vy"] = random.uniform(-0.2, 0.2)
            else:
                # Marines patrol around base
                u["vx"] += random.uniform(-0.08, 0.08)
                u["vy"] += random.uniform(-0.08, 0.08)
                u["vx"] = max(-0.6, min(0.6, u["vx"]))
                u["vy"] = max(-0.5, min(0.5, u["vy"]))
                # Gravitate toward base center
                cx, cy = 280, 260
                u["vx"] += (cx - u["x"]) * 0.0003
                u["vy"] += (cy - u["y"]) * 0.0003

            u["x"] += u["vx"]
            u["y"] += u["vy"]
            u["x"] = max(10, min(630, u["x"]))
            u["y"] = max(10, min(self.GAME_H - 10, u["y"]))

        # Resource ticking
        if t % 25 == 0:
            self.minerals += random.randint(1, 4)
        if t % 40 == 0:
            self.gas += random.randint(0, 2)
        marines = [u for u in self.units if u["type"] == "marine"]
        self.supply = min(self.supply_max, 5 + len(marines))

        # Occasionally spawn a marine from barracks
        rax = next((b for b in self.buildings if b["type"] == "rax"), None)
        if t % 180 == 0 and len(self.units) < 14 and rax:
            self.units.append({
                "x": float(rax["x"] + rax["w"] // 2),
                "y": float(rax["y"] + rax["h"] + 5),
                "vx": random.uniform(-0.2, 0.2), "vy": random.uniform(0.1, 0.3),
                "type": "marine", "color": (120, 170, 230), "size": 5, "hp": 1.0,
                "mining": False,
            })

        # Cycle selected unit
        if t % 60 == 0:
            self.selected_unit = (self.selected_unit + 1) % max(1, len(self.units))

        return self._render(t, action_idx)

    def _render(self, t, action_idx):
        frame = self.terrain.copy()

        # Fog of war — darken edges of game area (vectorized)
        if not hasattr(self, '_fog_mask'):
            Y, X = np.ogrid[:self.GAME_H, :640]
            dist = np.sqrt((X - 280.0)**2 + (Y - 240.0)**2)
            self._fog_mask = np.clip((dist - 200) / 250, 0, 0.6).astype(np.float32)
        fog = self._fog_mask
        game_area = frame[:self.GAME_H].astype(np.float32)
        for c in range(3):
            game_area[:, :, c] *= (1 - fog)
        frame[:self.GAME_H] = game_area.astype(np.uint8)

        # Mineral patches — blue crystals with shimmer
        for mp in self.mineral_patches:
            shimmer = 0.7 + 0.3 * math.sin(t * 0.06 + mp["x"] * 0.05)
            # Crystal shape: tall narrow ellipse
            color_base = (int(60 * shimmer), int(140 * shimmer), int(220 * shimmer))
            color_hi = (int(120 * shimmer), int(200 * shimmer), int(255 * shimmer))
            s = mp["size"]
            cv2.ellipse(frame, (int(mp["x"]), int(mp["y"])),
                        (s, int(s * 0.55)), 15, 0, 360, color_base, -1)
            # Bright highlight on crystal
            cv2.ellipse(frame, (int(mp["x"]) - 2, int(mp["y"]) - 2),
                        (s // 3, s // 4), 10, 0, 360, color_hi, -1)
            # Small sparkle
            if (t + mp["x"]) % 20 < 3:
                cv2.circle(frame, (int(mp["x"]) + s // 2, int(mp["y"]) - s // 3),
                           1, (200, 230, 255), -1)

        # Vespene geysers — green gas
        for g in self.geysers:
            cv2.ellipse(frame, (g["x"], g["y"]), (g["size"], int(g["size"] * 0.6)),
                        0, 0, 360, (30, 80, 30), -1)
            cv2.ellipse(frame, (g["x"], g["y"]), (g["size"], int(g["size"] * 0.6)),
                        0, 0, 360, (50, 120, 50), 1)
            # Gas plume animation
            plume_h = 5 + int(4 * math.sin(t * 0.1 + g["x"]))
            cv2.circle(frame, (g["x"], g["y"] - plume_h), 4,
                       (40, int(100 + 30 * math.sin(t * 0.15)), 40), -1)

        # Buildings — with shadow, shading, and structure detail
        for b in self.buildings:
            bx, by, bw, bh = b["x"], b["y"], b["w"], b["h"]

            # Drop shadow
            cv2.rectangle(frame, (bx + 3, by + 3), (bx + bw + 3, by + bh + 3),
                          b["shadow"], -1)
            # Main structure
            cv2.rectangle(frame, (bx, by), (bx + bw, by + bh), b["color"], -1)
            # Top edge highlight
            cv2.line(frame, (bx, by), (bx + bw, by), tuple(min(255, c + 40) for c in b["color"]), 1)
            # Dark bottom edge
            cv2.line(frame, (bx, by + bh), (bx + bw, by + bh), b["shadow"], 1)
            # Border
            cv2.rectangle(frame, (bx, by), (bx + bw, by + bh), (100, 130, 160), 1)

            # Building type detail
            if b["type"] == "cc":
                # Command Center — cross pattern
                cx, cy_ = bx + bw // 2, by + bh // 2
                cv2.line(frame, (cx - 12, cy_), (cx + 12, cy_), (110, 130, 155), 2)
                cv2.line(frame, (cx, cy_ - 10), (cx, cy_ + 10), (110, 130, 155), 2)
                # Rally flag
                cv2.circle(frame, (cx, by - 3), 3, (0, 200, 0), -1)
            elif b["type"] == "rax":
                # Barracks — door opening
                dx = bx + bw // 2 - 6
                cv2.rectangle(frame, (dx, by + bh - 12), (dx + 12, by + bh),
                              (55, 70, 90), -1)
            elif b["type"] == "depot":
                # Supply Depot — small box pattern
                cx, cy_ = bx + bw // 2, by + bh // 2
                cv2.rectangle(frame, (cx - 6, cy_ - 4), (cx + 6, cy_ + 4),
                              (65, 85, 108), -1)

            # HP bar
            hp_w = int(bw * b["hp"])
            cv2.rectangle(frame, (bx, by - 6), (bx + bw, by - 3), (20, 20, 20), -1)
            hp_color = (60, 200, 60) if b["hp"] > 0.5 else (200, 200, 60) if b["hp"] > 0.25 else (200, 60, 60)
            cv2.rectangle(frame, (bx, by - 6), (bx + hp_w, by - 3), hp_color, -1)

        # Units — with selection circles, wireframe overlays
        for idx_u, u in enumerate(self.units):
            ix, iy = int(u["x"]), int(u["y"])

            if u["type"] == "scv":
                # SCV: yellow-ish square body
                cv2.rectangle(frame, (ix - 4, iy - 4), (ix + 4, iy + 4), (180, 180, 70), -1)
                cv2.rectangle(frame, (ix - 4, iy - 4), (ix + 4, iy + 4), (220, 220, 100), 1)
                # Mining arm
                arm_angle = math.sin(t * 0.2 + ix * 0.1) * 0.5
                ax = ix + int(6 * math.cos(arm_angle))
                ay = iy + int(6 * math.sin(arm_angle))
                cv2.line(frame, (ix, iy), (ax, ay), (200, 200, 80), 1)
            else:
                # Marine: blue circle
                cv2.circle(frame, (ix, iy), 4, u["color"], -1)
                cv2.circle(frame, (ix, iy), 4, (160, 200, 250), 1)
                # Gun barrel direction
                gx = ix + int(5 * math.cos(u["vx"] * 3))
                gy = iy + int(5 * math.sin(u["vy"] * 3))
                cv2.line(frame, (ix, iy), (gx, gy), (180, 210, 240), 1)

            # Selection circle (green) for selected unit
            if idx_u == self.selected_unit:
                cv2.ellipse(frame, (ix, iy + 2), (8, 4), 0, 0, 360, (0, 255, 0), 1)

            # HP pip
            if u["hp"] < 1.0:
                cv2.rectangle(frame, (ix - 5, iy - 8), (ix + 5, iy - 6), (20, 20, 20), -1)
                cv2.rectangle(frame, (ix - 5, iy - 8),
                              (ix - 5 + int(10 * u["hp"]), iy - 6), (60, 200, 60), -1)

        # ─── HUD ───

        # Top resource bar (like SC1: minerals, gas, supply on dark bar)
        cv2.rectangle(frame, (0, 0), (640, 16), (12, 14, 18), -1)
        cv2.line(frame, (0, 16), (640, 16), (40, 50, 60), 1)
        # Mineral icon (blue diamond) + text
        cv2.circle(frame, (12, 8), 4, (60, 140, 220), -1)
        cv2.putText(frame, str(self.minerals), (22, 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (100, 200, 255), 1)
        # Gas icon (green circle) + text
        cv2.circle(frame, (100, 8), 4, (50, 180, 50), -1)
        cv2.putText(frame, str(self.gas), (110, 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (80, 220, 80), 1)
        # Supply
        cv2.putText(frame, f"{self.supply}/{self.supply_max}", (185, 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1)

        # Minimap (bottom-left, 128×105)
        mm_x, mm_y, mm_w, mm_h = 4, self.HUD_Y + 4, 128, 96
        cv2.rectangle(frame, (mm_x - 1, mm_y - 1), (mm_x + mm_w + 1, mm_y + mm_h + 1),
                      (50, 65, 80), 1)
        cv2.rectangle(frame, (mm_x, mm_y), (mm_x + mm_w, mm_y + mm_h), (20, 35, 20), -1)
        # Draw terrain overview on minimap
        for mp in self.mineral_patches:
            mx = mm_x + int(mp["x"] / 640 * mm_w)
            my = mm_y + int(mp["y"] / self.GAME_H * mm_h)
            cv2.circle(frame, (mx, my), 2, (60, 140, 220), -1)
        for g in self.geysers:
            gx = mm_x + int(g["x"] / 640 * mm_w)
            gy = mm_y + int(g["y"] / self.GAME_H * mm_h)
            cv2.circle(frame, (gx, gy), 2, (50, 180, 50), -1)
        for b in self.buildings:
            bx_ = mm_x + int(b["x"] / 640 * mm_w)
            by_ = mm_y + int(b["y"] / self.GAME_H * mm_h)
            cv2.rectangle(frame, (bx_, by_), (bx_ + 3, by_ + 2), (100, 130, 160), -1)
        for u in self.units:
            ux = mm_x + int(u["x"] / 640 * mm_w)
            uy = mm_y + int(u["y"] / self.GAME_H * mm_h)
            col = (0, 255, 0) if u["type"] == "scv" else (100, 180, 255)
            cv2.circle(frame, (ux, uy), 1, col, -1)
        # Viewport rectangle on minimap
        cv2.rectangle(frame, (mm_x + 10, mm_y + 15), (mm_x + 60, mm_y + 50),
                      (255, 255, 255), 1)

        # Info panel (bottom-center): shows selected unit info
        ip_x = 140
        cv2.line(frame, (ip_x, self.HUD_Y), (ip_x, 480), (40, 50, 60), 1)
        if self.selected_unit < len(self.units):
            su = self.units[self.selected_unit]
            name = "SCV" if su["type"] == "scv" else "Marine"
            cv2.putText(frame, name, (ip_x + 10, self.HUD_Y + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 210, 220), 1)
            cv2.putText(frame, f"HP: {int(su['hp'] * 100)}%", (ip_x + 10, self.HUD_Y + 38),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.32, (100, 200, 100), 1)
            cv2.putText(frame, f"Pos: ({int(su['x'])},{int(su['y'])})", (ip_x + 10, self.HUD_Y + 54),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.3, (150, 160, 170), 1)
            # Unit portrait placeholder
            cv2.rectangle(frame, (ip_x + 10, self.HUD_Y + 60), (ip_x + 60, self.HUD_Y + 96),
                          (40, 55, 70), -1)
            cv2.rectangle(frame, (ip_x + 10, self.HUD_Y + 60), (ip_x + 60, self.HUD_Y + 96),
                          (60, 80, 100), 1)
            cv2.putText(frame, su["type"][:3].upper(), (ip_x + 15, self.HUD_Y + 82),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (180, 190, 200), 1)

        # Command card (bottom-right): 3×3 grid of ability buttons
        cc_x = 480
        cv2.line(frame, (cc_x, self.HUD_Y), (cc_x, 480), (40, 50, 60), 1)
        btn_labels = ["M", "S", "P", "A", "H", "B", "", "", ""]
        for r in range(3):
            for c in range(3):
                bx_ = cc_x + 8 + c * 50
                by_ = self.HUD_Y + 8 + r * 30
                has_ability = (r * 3 + c) < 6
                bg = (30, 42, 55) if has_ability else (18, 22, 28)
                cv2.rectangle(frame, (bx_, by_), (bx_ + 44, by_ + 26), bg, -1)
                cv2.rectangle(frame, (bx_, by_), (bx_ + 44, by_ + 26), (50, 65, 80), 1)
                if has_ability:
                    lbl = btn_labels[r * 3 + c]
                    cv2.putText(frame, lbl, (bx_ + 4, by_ + 18),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (140, 170, 200), 1)

        # Agent action highlight (in game area)
        if 10 <= action_idx < 35:
            grid_idx = action_idx - 10
            col_i, row_i = grid_idx % 5, grid_idx // 5
            ax = int(64 + col_i * 128)
            ay = int(18 + row_i * (self.GAME_H // 5))
            r2 = 10 + int(3 * math.sin(t * 0.15))
            cv2.circle(frame, (ax, ay), r2, (0, 200, 255), 2)
            cv2.circle(frame, (ax, ay), r2 + 4, (0, 150, 200), 1)

        return frame

    def get_obs_84(self, frame):
        """Resize 640×480 to 84×84 RGB."""
        small = cv2.resize(frame, (84, 84), interpolation=cv2.INTER_AREA)
        return small


# ═══════════════════════════════════════════════════════════════════
# TRAINING SIMULATION ENGINE
# ═══════════════════════════════════════════════════════════════════

class TrainingSimulator:
    """Simulates distributed PPO training with real CNN forward passes."""

    def __init__(self):
        self.agent = CNNAgent(num_actions=35)
        # Try to load from latest checkpoint
        ckpt_path = os.path.join(DATA_DIR, "checkpoints", "model_latest.pt")
        if os.path.exists(ckpt_path):
            sd = torch.load(ckpt_path, map_location="cpu", weights_only=True)
            self.agent.load_state_dict(sd)
            print(f"Resumed from checkpoint: {ckpt_path}")
        self.agent.eval()
        self.optimizer = torch.optim.Adam(self.agent.parameters(), lr=2.5e-4, eps=1e-5)
        self.renderer = StarCraftRenderer()

        # State
        self.iteration = 0
        self.max_iterations = 999
        self.num_workers = 2
        self.rollout_steps = 128
        self.phase = "idle"  # idle, saving_model, rollout, ppo_update, checkpoint
        self.tick = 0

        # Worker state
        self.workers = [
            {"worker_id": i, "state": "idle", "step": 0, "total_reward": 0.0,
             "minerals": 50, "action_name": "—", "action_idx": -1}
            for i in range(self.num_workers)
        ]

        # Simulated scheduler
        self.jobs = []
        self.pods = []

        # Metrics
        self.metrics_history = []

        # Per-tick output (read by API endpoints)
        self.current_frame_b64 = None
        self.current_obs = None
        self.current_activations = None
        self.current_action_probs = None
        self.current_value = None
        self.current_fc_stats = None
        self.nn_active = False          # True only when a forward pass just ran
        self.last_forward_tick = -999   # tick when last forward pass happened

        # Menu navigation
        self._menu_navigated = False
        self._menu_thread = None

        # Real OpenEnv state
        self._has_real_env = False
        self._last_openenv_frame = None

        # Mineral-based reward tracking
        self._mineral_pid = None
        self._mineral_addr = None
        self._last_minerals = None
        self._mineral_scan_done = False
        self._mineral_scan_step = 0

        # Rollout buffers for real PPO training (worker 0)
        self._rollout_obs = np.zeros((self.rollout_steps, 84, 84, 3), dtype=np.uint8)
        self._rollout_actions = np.zeros(self.rollout_steps, dtype=np.int64)
        self._rollout_rewards = np.zeros(self.rollout_steps, dtype=np.float32)
        self._rollout_log_probs = np.zeros(self.rollout_steps, dtype=np.float32)
        self._rollout_values = np.zeros(self.rollout_steps, dtype=np.float32)
        self._rollout_dones = np.zeros(self.rollout_steps, dtype=np.float32)

        # Events log
        self.events = []

    def _add_event(self, etype, msg):
        ts = time.strftime("%H:%M:%S")
        self.events.insert(0, {"time": ts, "type": etype, "msg": msg})
        if len(self.events) > 60:
            self.events = self.events[:60]

    def _try_grab_real_frame(self):
        """Try to grab a single frame from a real OpenEnv instance (sync)."""
        if not WORKER_URLS or WORKER_URLS == ["http://localhost:8000"]:
            return None
        try:
            import httpx
            url = f"{WORKER_URLS[0].strip()}/stream"
            with httpx.Client() as client:
                with client.stream("GET", url, timeout=2) as r:
                    buf = b""
                    for chunk in r.iter_bytes(8192):
                        buf += chunk
                        start = buf.find(b"\xff\xd8")
                        end = buf.find(b"\xff\xd9", start + 2) if start >= 0 else -1
                        if start >= 0 and end >= 0:
                            jpg = buf[start:end + 2]
                            arr = np.frombuffer(jpg, dtype=np.uint8)
                            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                            return frame
                        if len(buf) > 500000:
                            break
        except Exception:
            pass
        return None

    def _remap_starcraft_window(self):
        """Remap StarCraft's X11 window if it got unmapped during a transition.

        StarCraft unmaps its window during loading screens / mode switches.
        Uses docker exec + xdotool to re-map window ID 8388609.
        """
        container = "openenv-starcraft"
        try:
            result = subprocess.run(
                ["docker", "exec", container, "bash", "-c",
                 "DISPLAY=:99 xwininfo -id 8388609 2>/dev/null | grep -c IsUnMapped"],
                capture_output=True, text=True, timeout=5)
            if result.stdout.strip() == "1":
                subprocess.run(
                    ["docker", "exec", container, "bash", "-c",
                     "DISPLAY=:99 xdotool windowmap 8388609"],
                    capture_output=True, timeout=5)
                print("Remapped StarCraft window (was unmapped)")
                return True
        except Exception as e:
            print(f"Window remap error: {e}")
        return False

    def _navigate_starcraft_menus(self, base_url: str):
        """Navigate StarCraft BW menus to start a custom melee game.

        Path: Main Menu → Single Player → Expansion → Profile Select →
              Episode Select → Play Custom → AIIDE folder → select map → Ok

        Runs in a background thread so it doesn't block the tick loop.
        """
        import requests

        def _step(action):
            try:
                requests.post(f"{base_url}/step", json=action, timeout=15)
            except Exception as e:
                print(f"Menu nav error: {e}")

        def _click(x, y):
            _step({"action_type": "mouse", "x": x, "y": y,
                    "button": "left", "mouse_state": "click"})
            time.sleep(0.5)

        def _get_brightness():
            """Get current screen brightness."""
            try:
                resp = requests.post(f"{base_url}/step",
                    json={"action_type": "noop"}, timeout=15)
                data = resp.json()
                screen_b64 = data.get("observation", {}).get("screen", "")
                if screen_b64:
                    jpg = base64.b64decode(screen_b64)
                    arr = np.frombuffer(jpg, dtype=np.uint8)
                    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    if frame is not None:
                        return frame.mean()
            except Exception:
                pass
            return 0

        def _save_replay_and_exit():
            """Handle the post-game defeat/victory screen sequence.

            Flow: score screen → click 'Save Replay' → type name →
                  click 'Save' (or press Return) → dismiss errors →
                  click 'Ok' on score → back to episode selection.
            """
            replay_name = f"ppo_iter{self.iteration}"
            print(f"  → Saving replay as '{replay_name}'...")

            # Click 'Save Replay' button (bottom center, ~x=380, y=395)
            _click(380, 395)
            time.sleep(2)

            b = _get_brightness()
            if b > 50:
                # Save Replay dialog opened — has text field + Save/Cancel
                # Clear existing text and type our replay name
                # Select all existing text, then type over it
                _step({"action_type": "key", "key": "ctrl+a"})
                time.sleep(0.3)
                for ch in replay_name:
                    _step({"action_type": "key", "key": ch})
                    time.sleep(0.05)
                time.sleep(0.5)

                # Click 'Save' button (~x=200, y=340)
                print(f"  → Clicking Save...")
                _click(200, 340)
                time.sleep(2)

                # Dismiss "Unable to write save file" error if it appears
                _step({"action_type": "key", "key": "Return"})
                time.sleep(1)
                _step({"action_type": "key", "key": "Return"})
                time.sleep(1)

                self._add_event("monitor",
                    f"Saved replay: {replay_name}")
            else:
                # Save Replay dialog didn't open; just dismiss score screen
                print("  → Save dialog did not appear, skipping save")
                _step({"action_type": "key", "key": "Return"})
                time.sleep(1)

            # Press Return / Ok to close the score screen
            _step({"action_type": "key", "key": "Return"})
            time.sleep(2)
            _step({"action_type": "key", "key": "Return"})
            time.sleep(2)

        def _start_new_game():
            """From episode selection, start a new custom game on AIIDE maps."""
            print("  → Play Custom (click 300, 385)")
            _click(300, 385)
            time.sleep(3)

            print("  → Select AIIDE folder (Down + Return)")
            _step({"action_type": "key", "key": "Down"})
            time.sleep(1)
            _step({"action_type": "key", "key": "Return"})
            time.sleep(3)

            print("  → Ok button (click 510, 375)")
            _click(510, 375)
            time.sleep(15)  # wait for game to load

            print("  → Dismiss tips (click OK)")
            _click(230, 260)
            time.sleep(3)

        try:
            self._add_event("monitor", "Navigating StarCraft menus...")
            print("Navigating StarCraft menus to start custom game...")

            time.sleep(3)

            # --- Phase 1: Handle post-game state (save replay, exit score) ---
            b = _get_brightness()
            print(f"  Current brightness: {b:.1f}")

            if 20 < b < 45:
                # Likely on a defeat/score screen — try to save replay
                _save_replay_and_exit()
                b = _get_brightness()
                print(f"  After save+exit: {b:.1f}")

            # If still on a dialog or intermediate screen, mash Escape
            # to get back to a known state (main menu)
            if b < 50:
                print("  → Escaping to main menu...")
                for _ in range(5):
                    _step({"action_type": "key", "key": "Escape"})
                    time.sleep(1.5)
                b = _get_brightness()
                print(f"  After Escape: {b:.1f}")

            # --- Phase 2: Check if we are already at episode selection ---
            # Episode selection has brightness ~17 with Terran/Protoss/Zerg.
            # Main menu has brightness ~21.
            # If we're at episode selection (came from defeat), go straight
            # to Play Custom. Otherwise start from main menu.
            if b > 50:
                # Already in game somehow — skip navigation
                print("  Game already in-progress, skipping menu navigation")
                self._add_event("monitor", "Game already running")
            elif 14 < b < 19:
                # Looks like episode selection — go directly to Play Custom
                print("  At episode selection, starting game directly")
                _start_new_game()
            else:
                # At main menu or unknown — do full navigation
                print("  → Single Player (s)")
                _step({"action_type": "key", "key": "s"})
                time.sleep(3)

                print("  → Expansion (e)")
                _step({"action_type": "key", "key": "e"})
                time.sleep(3)

                print("  → Select profile (Return)")
                _step({"action_type": "key", "key": "Return"})
                time.sleep(3)

                _start_new_game()

            self._add_event("monitor", "StarCraft game started!")
            print("Menu navigation complete — game should be starting.")
        except Exception as e:
            print(f"Menu navigation failed: {e}")
            self._add_event("monitor", f"Menu nav failed: {e}")

    def _step_openenv(self, base_url, action_dict):
        """POST an action to OpenEnv /step and return (frame_640, reward).

        Returns (None, 0.0) on failure.
        """
        try:
            resp = http_requests.post(
                f"{base_url}/step", json=action_dict, timeout=15)
            data = resp.json()
            obs = data.get("observation", {})
            reward = float(data.get("reward", 0) or 0)
            screen_b64 = obs.get("screen", "")
            if screen_b64:
                jpg_bytes = base64.b64decode(screen_b64)
                arr = np.frombuffer(jpg_bytes, dtype=np.uint8)
                frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if frame is not None:
                    return frame, reward
        except Exception as e:
            print(f"OpenEnv /step error: {e}")
        return None, 0.0

    def _reset_game(self, base_url):
        """Reset the OpenEnv game, wait for health, re-navigate menus."""
        try:
            self._add_event("monitor", "Resetting OpenEnv game...")
            print("Resetting OpenEnv game...")
            http_requests.post(f"{base_url}/reset", timeout=30)
        except Exception as e:
            print(f"Reset POST failed: {e}")

        # Poll /health until ready (up to ~30s)
        for _ in range(30):
            time.sleep(1)
            try:
                r = http_requests.get(f"{base_url}/health", timeout=3)
                if r.status_code == 200:
                    break
            except Exception:
                pass

        # Re-navigate menus
        self._menu_navigated = False
        self._menu_thread = None

    def _init_mineral_tracking(self, base_url):
        """Find StarCraft PID and scan for mineral address."""
        try:
            r = http_requests.get(f"{base_url}/process/StarCraft.exe", timeout=5)
            if r.status_code == 200:
                self._mineral_pid = r.json()["pid"]
                # Scan for starting mineral value (50)
                r2 = http_requests.post(f"{base_url}/memory/scan", json={
                    "pid": self._mineral_pid, "value": 50, "value_type": "int"
                }, timeout=10)
                if r2.status_code == 200:
                    data = r2.json()
                    if data.get("count", 0) > 0:
                        self._mineral_addr = data["addresses"][0]
                        self._add_event("monitor", f"Found mineral address: {self._mineral_addr}")
                        print(f"Mineral tracking: pid={self._mineral_pid} addr={self._mineral_addr}")
                        return
            print("Mineral tracking: could not find address")
        except Exception as e:
            print(f"Mineral tracking init failed: {e}")

    def _read_minerals(self, base_url):
        """Read current mineral count from game memory. Returns int or None."""
        if self._mineral_pid is None or self._mineral_addr is None:
            return None
        try:
            r = http_requests.post(f"{base_url}/memory/read", json={
                "pid": self._mineral_pid, "address": self._mineral_addr, "size": 4
            }, timeout=5)
            if r.status_code == 200:
                data_b64 = r.json()["data_b64"]
                raw = base64.b64decode(data_b64)
                return struct.unpack("<i", raw)[0]
        except Exception:
            pass
        return None

    def _compute_mineral_reward(self, base_url):
        """Compute reward from mineral delta. Returns float."""
        minerals = self._read_minerals(base_url)
        reward = -0.001  # time penalty
        if minerals is not None:
            if self._last_minerals is not None:
                delta = minerals - self._last_minerals
                reward += delta * 0.01
            self._last_minerals = minerals
        return reward

    def _run_forward(self, obs_84):
        """Run real CNN forward pass and cache results."""
        obs_tensor = torch.from_numpy(obs_84).unsqueeze(0)
        with torch.no_grad():
            acts = self.agent.get_activations(obs_tensor)

        self.last_forward_tick = self.tick
        self.nn_active = True
        self.current_obs = obs_84
        self.current_action_probs = acts["action_probs"][0].numpy().tolist()
        self.current_value = acts["value"][0].item()
        fc = acts["fc"][0]
        self.current_fc_stats = {
            "mean": fc.mean().item(),
            "std": fc.std().item(),
            "max": fc.max().item(),
            "sparsity": (fc == 0).float().mean().item(),
        }

        # Build activation maps for API
        result = {}
        for layer in ["conv1", "conv2", "conv3"]:
            tensor = acts[layer][0].numpy()
            maps = []
            for i in range(tensor.shape[0]):
                filt = tensor[i]
                fmin, fmax = filt.min(), filt.max()
                if fmax - fmin > 1e-6:
                    filt = ((filt - fmin) / (fmax - fmin) * 255).astype(np.uint8)
                else:
                    filt = np.zeros_like(filt, dtype=np.uint8)
                maps.append(filt.tolist())
            result[layer] = {"shape": list(tensor.shape), "maps": maps}
        self.current_activations = result

    def _encode_frame(self, frame):
        """Encode 640×480 frame to base64 JPEG."""
        _, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return base64.b64encode(jpg.tobytes()).decode()

    def _run_ppo_update(self):
        """Run real PPO update on collected rollout data.

        Returns dict with policy_loss, value_loss, entropy (or None if no data).
        """
        if not self._has_real_env:
            # Fallback: fake update for simulation mode
            obs = torch.randint(0, 255, (8, 84, 84, 3), dtype=torch.uint8)
            obs_f = obs.permute(0, 3, 1, 2).float() / 255.0
            self.agent.train()
            hidden = self.agent.network(obs_f)
            logits = self.agent.actor(hidden)
            values = self.agent.critic(hidden)
            loss = -logits.mean() * 0.001 + values.mean() * 0.001
            self.optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.agent.parameters(), 0.5)
            self.optimizer.step()
            self.agent.eval()
            return None

        # Compute next value for GAE
        last_frame = self._last_openenv_frame
        if last_frame is not None:
            obs_84 = self.renderer.get_obs_84(last_frame)
            obs_tensor = torch.from_numpy(obs_84).unsqueeze(0)
            with torch.no_grad():
                next_value = self.agent.get_value(obs_tensor).item()
        else:
            next_value = 0.0

        # Compute GAE advantages
        advantages, returns = compute_gae(
            self._rollout_rewards, self._rollout_values,
            self._rollout_dones, next_value,
        )

        # Convert to tensors
        obs_t = torch.from_numpy(self._rollout_obs)
        actions_t = torch.from_numpy(self._rollout_actions)
        log_probs_t = torch.from_numpy(self._rollout_log_probs)
        advantages_t = torch.from_numpy(advantages)
        returns_t = torch.from_numpy(returns)

        # Run PPO update
        self.agent.train()
        stats = ppo_update(
            self.agent, self.optimizer,
            obs_t, actions_t, log_probs_t,
            advantages_t, returns_t,
        )
        self.agent.eval()
        return stats

    def tick_step(self):
        """Advance simulation by one tick (~200ms)."""
        self.tick += 1

        # Mark NN as inactive unless a forward pass happens this tick
        self.nn_active = False

        # Try to grab a real frame from OpenEnv and run CNN on it
        self._has_real_frame = False
        real_frame = self._try_grab_real_frame()
        if real_frame is not None:
            self._has_real_frame = True
            self._has_real_env = True
            if self._last_openenv_frame is None:
                self._last_openenv_frame = real_frame
            obs_84 = self.renderer.get_obs_84(real_frame)
            self._run_forward(obs_84)
            self.current_frame_b64 = self._encode_frame(real_frame)

            # Auto-navigate StarCraft menus on first real frame
            # or re-navigate if screen goes blank (agent exited to menus)
            menu_thread_done = (self._menu_thread is not None and
                                not self._menu_thread.is_alive())
            if not self._menu_navigated and self._menu_thread is None:
                # Skip menu nav if game is already in-progress (bright screen)
                if real_frame is not None and real_frame.mean() > 40:
                    print("Game already in-progress, skipping menu navigation")
                    self._menu_navigated = True
                    self._last_nav_tick = self.tick
                else:
                    self._menu_navigated = True
                    self._last_nav_tick = self.tick
                    base_url = WORKER_URLS[0].strip()
                    self._menu_thread = threading.Thread(
                        target=self._navigate_starcraft_menus,
                        args=(base_url,), daemon=True)
                    self._menu_thread.start()
            elif menu_thread_done and self.tick % 100 == 0:
                # Check for blank/dark screen → game may have exited
                # (persistent remap loop handles window unmapping,
                #  so dark frames here mean the game genuinely ended)
                ticks_since_nav = self.tick - getattr(self, '_last_nav_tick', 0)
                mean_brightness = real_frame.mean()
                if mean_brightness < 15 and ticks_since_nav > 500:
                    self._add_event("monitor", "Extended dark screen, re-navigating menus...")
                    print(f"Extended dark screen (brightness={mean_brightness:.1f}) — re-navigating menus")
                    self._menu_navigated = False
                    self._menu_thread = None
                    self._mineral_scan_done = False
                    self._last_minerals = None
        else:
            # Fallback: render procedural frame
            frame = self.renderer.step(-1)
            self.current_frame_b64 = self._encode_frame(frame)

        if self.phase == "idle":
            self.phase = "saving_model"
            self._add_event("trainer", f"Saving model.pt (iter {self.iteration})")
            self._update_scheduler("saving_model")

        elif self.phase == "saving_model":
            if self.tick % 3 == 0:
                # Don't reset between iterations — keep playing the same game.
                # Reset only happens when training wraps around (max_iterations).
                self.phase = "rollout"
                for w in self.workers:
                    w["state"] = "boot"
                    w["step"] = 0
                    w["total_reward"] = 0.0
                    w["minerals"] = 50
                self._add_event("kueue", f"Created {self.num_workers} worker jobs")
                self._add_event("kueue", "Admitting workers to training-queue")
                self._update_scheduler("rollout_boot")

        elif self.phase == "rollout":
            any_collecting = False
            all_done = True

            for w in self.workers:
                if w["state"] == "boot":
                    # Boot takes a few ticks
                    w["step"] += 1
                    if w["step"] >= 5:
                        w["state"] = "collect"
                        w["step"] = 0
                        # Init mineral tracking for worker 0
                        if w["worker_id"] == 0 and self._has_real_env and not self._mineral_scan_done:
                            base_url = WORKER_URLS[0].strip()
                            self._init_mineral_tracking(base_url)
                            self._mineral_scan_done = True
                        self._add_event("worker", f"Worker {w['worker_id']} OpenEnv ready, collecting")
                        self._update_scheduler("rollout_collect")
                    all_done = False

                elif w["state"] == "collect":
                    any_collecting = True
                    all_done = False

                    if w["worker_id"] == 0 and self._has_real_env:
                        # ── Worker 0: real OpenEnv interaction (1 step per tick) ──
                        if w["step"] < self.rollout_steps:
                            base_url = WORKER_URLS[0].strip()
                            step_idx = w["step"]

                            # Use last frame from /step (or grabbed frame on first step)
                            frame = self._last_openenv_frame
                            if frame is not None:
                                obs_84 = self.renderer.get_obs_84(frame)
                                self._run_forward(obs_84)
                                self.current_frame_b64 = self._encode_frame(frame)

                                # Store observation for PPO
                                self._rollout_obs[step_idx] = obs_84

                                # Get action + log_prob + value from policy
                                obs_tensor = torch.from_numpy(obs_84).unsqueeze(0)
                                with torch.no_grad():
                                    action_t, log_prob_t, _, value_t = self.agent.get_action_and_value(obs_tensor)

                                # Epsilon-greedy: 90% policy, 10% random
                                if random.random() < 0.9:
                                    action_idx = action_t.item()
                                else:
                                    action_idx = random.randint(0, 34)
                                    # Recompute log_prob for random action
                                    with torch.no_grad():
                                        _, log_prob_t, _, _ = self.agent.get_action_and_value(
                                            obs_tensor, torch.tensor([action_idx]))

                                self._rollout_actions[step_idx] = action_idx
                                self._rollout_log_probs[step_idx] = log_prob_t.item()
                                self._rollout_values[step_idx] = value_t.item()
                            else:
                                action_idx = random.randint(0, 34)

                            # POST action to OpenEnv
                            action_dict = ALL_ACTIONS[action_idx]
                            next_frame, _step_reward = self._step_openenv(base_url, action_dict)
                            if next_frame is not None:
                                self._last_openenv_frame = next_frame

                                # Track consecutive non-gameplay frames to detect
                                # game-over vs transient window unmap flicker.
                                # Gameplay is typically brightness 50-80.
                                # Menus/score screens are 15-40. Unmapped is <10.
                                frame_brightness = next_frame.mean()
                                if frame_brightness < 45:
                                    self._dark_frame_count = getattr(self, '_dark_frame_count', 0) + 1
                                else:
                                    self._dark_frame_count = 0

                                # Only trigger game-over after 8+ consecutive non-gameplay frames
                                if self._dark_frame_count >= 8 and step_idx > 10:
                                    self._rollout_dones[step_idx] = 1.0
                                    self._add_event("monitor", f"Game over detected ({self._dark_frame_count} dark frames)")
                                    print(f"Game over at step {step_idx} ({self._dark_frame_count} consecutive dark frames)")
                                    self._menu_navigated = False
                                    self._menu_thread = None
                                    self._mineral_scan_done = False
                                    self._last_minerals = None
                                    self._dark_frame_count = 0
                                else:
                                    self._rollout_dones[step_idx] = 0.0
                            else:
                                self._rollout_dones[step_idx] = 0.0

                            # Compute mineral-based reward
                            reward = self._compute_mineral_reward(base_url)
                            self._rollout_rewards[step_idx] = reward

                            self.nn_active = True
                            w["step"] += 1
                            w["total_reward"] += reward
                            minerals = self._read_minerals(base_url)
                            w["minerals"] = minerals if minerals is not None else self.renderer.minerals
                            a = ALL_ACTIONS[action_idx]
                            if a["action_type"] == "key":
                                w["action_name"] = f"key:{a['key']}"
                            else:
                                w["action_name"] = f"click({a['x']},{a['y']})"
                            w["action_idx"] = action_idx
                    else:
                        # ── Workers 1-N (or no real env): simulated collection ──
                        steps_per_tick = random.randint(3, 8)
                        for _ in range(steps_per_tick):
                            if w["step"] >= self.rollout_steps:
                                break
                            action_idx = random.randint(0, 34)
                            if w["worker_id"] == 0 and not self._has_real_frame:
                                frame = self.renderer.step(action_idx)
                                obs_84 = self.renderer.get_obs_84(frame)
                                self._run_forward(obs_84)
                                self.current_frame_b64 = self._encode_frame(frame)
                                if self.current_action_probs:
                                    action_idx = int(np.argmax(self.current_action_probs))

                            reward = random.uniform(-0.002, 0.005)
                            w["step"] += 1
                            w["total_reward"] += reward
                            w["minerals"] = self.renderer.minerals
                            a = ALL_ACTIONS[action_idx]
                            if a["action_type"] == "key":
                                w["action_name"] = f"key:{a['key']}"
                            else:
                                w["action_name"] = f"click({a['x']},{a['y']})"
                            w["action_idx"] = action_idx

                    if w["step"] >= self.rollout_steps:
                        w["state"] = "saving"
                        self._add_event("worker", f"Worker {w['worker_id']} collected {self.rollout_steps} steps")

                elif w["state"] == "saving":
                    all_done = False
                    w["state"] = "done"
                    self._add_event("worker", f"Worker {w['worker_id']} saved .npz + .done")
                    self._update_scheduler("worker_done", w["worker_id"])

                elif w["state"] == "done":
                    pass  # already done

            if all_done and all(w["state"] == "done" for w in self.workers):
                self.phase = "ppo_update"
                self._add_event("trainer", "All workers done, starting PPO update")
                self._update_scheduler("ppo_update")

        elif self.phase == "ppo_update":
            # Run real PPO update on collected rollout data
            stats = self._run_ppo_update()
            avg_reward = sum(w["total_reward"] for w in self.workers) / self.num_workers

            if stats is not None:
                # Real PPO metrics
                pl = stats["policy_loss"]
                vl = stats["value_loss"]
                ent = stats["entropy"]
            else:
                # Simulated metrics fallback
                decay = math.exp(-self.iteration * 0.3)
                pl = 0.45 * decay + random.uniform(-0.02, 0.02)
                vl = 0.28 * decay + random.uniform(-0.015, 0.015)
                ent = 3.55 - self.iteration * 0.35 + random.uniform(-0.05, 0.05)

            self.metrics_history.append({
                "iteration": self.iteration,
                "policy_loss": max(0.001, pl),
                "value_loss": max(0.001, vl),
                "entropy": max(0.1, ent),
                "reward": avg_reward,
                "timestamp": time.time(),
            })

            stats_str = f"pl={pl:.4f} vl={vl:.4f} ent={ent:.3f} reward={avg_reward:.4f}"
            self._add_event("trainer", f"PPO update: {stats_str}")
            print(f"[iter {self.iteration}] PPO: {stats_str}")
            self.phase = "checkpoint"

        elif self.phase == "checkpoint":
            # Save model to disk
            ckpt_dir = os.path.join(DATA_DIR, "checkpoints")
            os.makedirs(ckpt_dir, exist_ok=True)
            ckpt_path = os.path.join(ckpt_dir, f"model_iter_{self.iteration}.pt")
            torch.save(self.agent.state_dict(), ckpt_path)
            # Also save as "latest" for easy resume
            torch.save(self.agent.state_dict(), os.path.join(ckpt_dir, "model_latest.pt"))
            self._add_event("trainer", f"Saved checkpoint model_iter_{self.iteration}.pt")
            self.iteration += 1
            self._update_scheduler("checkpoint")

            if self.iteration >= self.max_iterations:
                self._add_event("trainer", "Training complete! Restarting demo...")
                self.iteration = 0
                self.metrics_history = []
                self._menu_navigated = False
                self._menu_thread = None
                self._last_openenv_frame = None
                self._mineral_scan_done = False
                self._last_minerals = None

            self.phase = "idle"
            self._update_scheduler("idle")

    def _update_scheduler(self, phase, worker_id=None):
        """Generate realistic Kueue scheduler state."""
        self.jobs = []
        self.pods = []

        # Trainer job
        trainer_active = phase not in ("idle",)
        self.jobs.append({
            "name": "ppo-trainer",
            "labels": {"app": "ppo-trainer"},
            "suspended": False,
            "active": 1 if trainer_active else 0,
            "succeeded": 0,
            "failed": 0,
            "startTime": "2024-01-01T00:00:00Z",
            "completionTime": None,
        })
        if trainer_active:
            self.pods.append({
                "name": f"ppo-trainer-{random.randint(1000,9999)}",
                "labels": {"app": "ppo-trainer"},
                "phase": "Running",
                "containers": [
                    {"name": "trainer", "ready": True, "state": "running", "restartCount": 0},
                ],
                "nodeName": "kueue-demo-control-plane",
            })

        # Worker jobs
        for w in self.workers:
            wid = w["worker_id"]
            state = w["state"]
            is_active = state in ("boot", "collect", "saving")
            is_done = state == "done"

            self.jobs.append({
                "name": f"rollout-worker-{self.iteration}-{wid}",
                "labels": {"app": "rollout-worker", "worker-id": str(wid)},
                "suspended": state == "idle",
                "active": 1 if is_active else 0,
                "succeeded": 1 if is_done else 0,
                "failed": 0,
                "startTime": "2024-01-01T00:00:00Z" if not (state == "idle") else None,
                "completionTime": "2024-01-01T00:05:00Z" if is_done else None,
            })

            if is_active:
                openenv_ready = state != "boot"
                worker_ready = state == "collect"
                self.pods.append({
                    "name": f"rollout-worker-{self.iteration}-{wid}-{random.randint(1000,9999)}",
                    "labels": {"app": "rollout-worker", "worker-id": str(wid)},
                    "phase": "Running",
                    "containers": [
                        {"name": "worker", "ready": worker_ready, "state": "running", "restartCount": 0},
                        {"name": "openenv (sidecar)", "ready": openenv_ready,
                         "state": "running" if openenv_ready else "waiting", "restartCount": 0},
                    ],
                    "nodeName": "kueue-demo-control-plane",
                })

    def get_trainer_state(self):
        latest_stats = self.metrics_history[-1] if self.metrics_history else None
        phase_name = self.phase
        for w in self.workers:
            if w["state"] == "collect":
                phase_name = "rollout"
                break
        return {
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "phase": phase_name,
            "workers_done": sum(1 for w in self.workers if w["state"] == "done"),
            "num_workers": self.num_workers,
            "stats": latest_stats,
            "nn_active": self.nn_active,
            "timestamp": time.time(),
        }

    def get_workers_state(self):
        result = []
        for w in self.workers:
            total_steps = self.rollout_steps
            phase = w["state"]
            if phase == "idle":
                phase = "idle"
            elif phase == "boot":
                phase = "boot"
            elif phase == "collect":
                phase = "collect"
            elif phase == "saving":
                phase = "saving"
            elif phase == "done":
                phase = "done"

            result.append({
                "worker_id": w["worker_id"],
                "iteration": self.iteration,
                "step": w["step"],
                "total_steps": total_steps,
                "action_name": w["action_name"],
                "action_idx": w["action_idx"],
                "reward": 0.0,
                "total_reward": w["total_reward"],
                "minerals": w["minerals"],
                "phase": phase,
                "value": self.current_value,
                "timestamp": time.time(),
            })
        return result

    def get_scheduler_state(self):
        active_workers = sum(1 for w in self.workers if w["state"] in ("boot", "collect", "saving"))
        pending = sum(1 for w in self.workers if w["state"] == "idle" and self.phase == "rollout")
        cpu_used = 0.5 + active_workers * 1.5
        mem_gb = 0.5 + active_workers * 1.0
        return {
            "workloads": [],
            "jobs": self.jobs,
            "pods": self.pods,
            "queues": {
                "admittedWorkloads": 1 + active_workers,
                "pendingWorkloads": pending,
                "usage": [{
                    "name": "default-flavor",
                    "resources": [
                        {"name": "cpu", "total": str(cpu_used)},
                        {"name": "memory", "total": f"{mem_gb:.1f}Gi"},
                    ],
                }],
            },
        }


# ═══════════════════════════════════════════════════════════════════
# GLOBAL SIM + BACKGROUND THREAD
# ═══════════════════════════════════════════════════════════════════

SIM = TrainingSimulator()
_sim_running = False


def _sim_loop():
    """Background thread running the training simulation."""
    global _sim_running
    _sim_running = True
    while _sim_running:
        SIM.tick_step()
        time.sleep(0.2)  # 5 ticks/sec


def _start_persistent_remap():
    """Start a smart background process in the Docker container that keeps
    the StarCraft window mapped after it has been shown at least once.

    StarCraft/Wine calls XUnmapWindow on every screen transition.
    A naive always-remap loop breaks StarCraft startup (BadWindow error).
    This smart loop only remaps after the window was mapped at least once."""
    try:
        subprocess.Popen(
            ["docker", "exec", "-d", "openenv-starcraft", "bash", "-c",
             'was_mapped=0; '
             'while true; do '
             '  wid=$(DISPLAY=:99 xdotool search --name "Brood War" 2>/dev/null | head -1); '
             '  if [ -n "$wid" ]; then '
             '    state=$(DISPLAY=:99 xwininfo -id $wid 2>/dev/null | grep "Map State"); '
             '    if echo "$state" | grep -q "IsViewable"; then '
             '      was_mapped=1; '
             '    elif echo "$state" | grep -q "IsUnMapped" && [ "$was_mapped" = "1" ]; then '
             '      DISPLAY=:99 xdotool windowmap $wid 2>/dev/null; '
             '    fi; '
             '  fi; '
             '  sleep 0.5; '
             'done'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("Started persistent smart window-remap loop in container")
    except Exception as e:
        print(f"Could not start remap loop: {e}")


@app.on_event("startup")
async def startup():
    _start_persistent_remap()
    thread = threading.Thread(target=_sim_loop, daemon=True)
    thread.start()
    print("Training simulation started")


# ═══════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@app.get("/")
async def dashboard():
    return FileResponse(DASHBOARD_PATH, media_type="text/html")


@app.get("/api/stream/{worker_id}")
async def stream_proxy(worker_id: int):
    """MJPEG stream from real OpenEnv or simulation."""
    # Try real worker MJPEG stream first
    if worker_id < len(WORKER_URLS):
        url = f"{WORKER_URLS[worker_id].strip()}/stream"
        try:
            import httpx
            # Quick health check
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{WORKER_URLS[worker_id].strip()}/health", timeout=2)
                if r.status_code == 200:
                    async def proxy():
                        async with httpx.AsyncClient() as c:
                            async with c.stream("GET", url, timeout=None) as resp:
                                async for chunk in resp.aiter_bytes(4096):
                                    yield chunk
                    return StreamingResponse(proxy(), media_type="multipart/x-mixed-replace; boundary=frame")
        except Exception as e:
            print(f"Stream proxy failed for {url}: {e}")

    # Fall back to simulation MJPEG
    async def sim_stream():
        while True:
            if SIM.current_frame_b64:
                jpg_bytes = base64.b64decode(SIM.current_frame_b64)
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" +
                       jpg_bytes + b"\r\n")
            await asyncio.sleep(0.1)

    return StreamingResponse(sim_stream(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/game_frame/{worker_id}")
async def game_frame(worker_id: int):
    """Latest game frame as base64 JPEG."""
    # Try real OpenEnv MJPEG stream — grab one frame
    if worker_id < len(WORKER_URLS):
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                async with client.stream("GET", f"{WORKER_URLS[worker_id].strip()}/stream", timeout=3) as r:
                    buf = b""
                    async for chunk in r.aiter_bytes(8192):
                        buf += chunk
                        start = buf.find(b"\xff\xd8")
                        end = buf.find(b"\xff\xd9", start + 2) if start >= 0 else -1
                        if start >= 0 and end >= 0:
                            jpg = buf[start:end + 2]
                            return {"frame": base64.b64encode(jpg).decode(), "shape": [480, 640, 3], "source": "live"}
                        if len(buf) > 500000:
                            break
        except Exception:
            pass

    # Try real snapshot file
    snap_path = os.path.join(DATA_DIR, "monitor", "snapshots", f"worker_{worker_id}_obs.npy")
    if os.path.exists(snap_path):
        try:
            obs = np.load(snap_path)
            obs_bgr = cv2.cvtColor(obs, cv2.COLOR_RGB2BGR)
            obs_large = cv2.resize(obs_bgr, (336, 336), interpolation=cv2.INTER_NEAREST)
            _, jpg = cv2.imencode(".jpg", obs_large, [cv2.IMWRITE_JPEG_QUALITY, 85])
            return {"frame": base64.b64encode(jpg.tobytes()).decode(), "shape": list(obs.shape)}
        except Exception:
            pass

    # Simulation fallback
    if SIM.current_frame_b64:
        return {"frame": SIM.current_frame_b64, "shape": [480, 640, 3]}
    return {"frame": None}


@app.get("/api/activations/{worker_id}")
async def get_activations(worker_id: int):
    if SIM.current_activations:
        return SIM.current_activations
    return {}


@app.get("/api/activations_live/{worker_id}")
async def get_activations_live(worker_id: int):
    """Real CNN activations from simulation or live data."""
    # Try real model + snapshot first
    model_path = os.path.join(DATA_DIR, "model.pt")
    snap_path = os.path.join(DATA_DIR, "monitor", "snapshots", f"worker_{worker_id}_obs.npy")
    if os.path.exists(model_path) and os.path.exists(snap_path):
        try:
            agent = CNNAgent(num_actions=35)
            sd = torch.load(model_path, map_location="cpu", weights_only=True)
            agent.load_state_dict(sd)
            agent.eval()
            obs = np.load(snap_path)
            obs_t = torch.from_numpy(obs).unsqueeze(0)
            acts = agent.get_activations(obs_t)
            result = {}
            for layer in ["conv1", "conv2", "conv3"]:
                arr = acts[layer][0].numpy()
                maps = []
                for i in range(arr.shape[0]):
                    f = arr[i]
                    mn, mx = f.min(), f.max()
                    if mx - mn > 1e-6:
                        f = ((f - mn) / (mx - mn) * 255).astype(np.uint8)
                    else:
                        f = np.zeros_like(f, dtype=np.uint8)
                    maps.append(f.tolist())
                result[layer] = {"shape": list(arr.shape), "maps": maps}
            result["action_probs"] = acts["action_probs"][0].tolist()
            result["value"] = acts["value"][0].item()
            fc = acts["fc"][0]
            result["fc_stats"] = {
                "mean": fc.mean().item(), "std": fc.std().item(),
                "max": fc.max().item(), "sparsity": (fc == 0).float().mean().item(),
            }
            return result
        except Exception:
            pass

    # Simulation fallback
    if SIM.current_activations:
        r = dict(SIM.current_activations)
        if SIM.current_action_probs:
            r["action_probs"] = SIM.current_action_probs
        if SIM.current_value is not None:
            r["value"] = SIM.current_value
        if SIM.current_fc_stats:
            r["fc_stats"] = SIM.current_fc_stats
        return r
    return {"error": "no data yet"}


@app.get("/api/workers")
async def get_workers():
    # Try real data first
    state_dir = os.path.join(DATA_DIR, "monitor", "workers")
    if os.path.isdir(state_dir):
        workers = []
        for fname in sorted(os.listdir(state_dir)):
            if fname.endswith(".json"):
                try:
                    with open(os.path.join(state_dir, fname)) as f:
                        workers.append(json.load(f))
                except Exception:
                    pass
        if workers:
            return {"workers": workers}
    return {"workers": SIM.get_workers_state()}


@app.get("/api/metrics")
async def get_metrics():
    mp = os.path.join(DATA_DIR, "monitor", "metrics.json")
    if os.path.exists(mp):
        try:
            with open(mp) as f:
                real = json.load(f)
            if real:
                return {"metrics": real}
        except Exception:
            pass
    return {"metrics": SIM.metrics_history}


@app.get("/api/trainer")
async def get_trainer():
    sp = os.path.join(DATA_DIR, "monitor", "trainer.json")
    if os.path.exists(sp):
        try:
            with open(sp) as f:
                real = json.load(f)
            if real.get("phase") != "unknown":
                return real
        except Exception:
            pass
    return SIM.get_trainer_state()


@app.get("/api/scheduler")
async def get_scheduler():
    """Query real K8s or return simulation state."""
    # Try real K8s
    try:
        proc = await asyncio.create_subprocess_exec(
            "kubectl", "get", "jobs", "-n", NAMESPACE, "-o", "json",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            data = json.loads(stdout)
            if data.get("items"):
                # Real data exists, return full K8s state
                result = {"workloads": [], "jobs": [], "pods": [], "queues": {}}
                for item in data["items"]:
                    m = item.get("metadata", {})
                    s = item.get("status", {})
                    sp = item.get("spec", {})
                    result["jobs"].append({
                        "name": m.get("name", ""), "labels": m.get("labels", {}),
                        "suspended": sp.get("suspend", False),
                        "active": s.get("active", 0), "succeeded": s.get("succeeded", 0),
                        "failed": s.get("failed", 0),
                    })
                # Get pods too
                p2 = await asyncio.create_subprocess_exec(
                    "kubectl", "get", "pods", "-n", NAMESPACE, "-o", "json",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                so2, _ = await p2.communicate()
                if p2.returncode == 0:
                    pd = json.loads(so2)
                    for item in pd.get("items", []):
                        m = item.get("metadata", {})
                        st = item.get("status", {})
                        containers = []
                        for cs in st.get("containerStatuses", []) + st.get("initContainerStatuses", []):
                            sk = list(cs.get("state", {}).keys())
                            containers.append({
                                "name": cs.get("name", ""), "ready": cs.get("ready", False),
                                "state": sk[0] if sk else "unknown",
                                "restartCount": cs.get("restartCount", 0),
                            })
                        result["pods"].append({
                            "name": m.get("name", ""), "labels": m.get("labels", {}),
                            "phase": st.get("phase", "Unknown"), "containers": containers,
                            "nodeName": item.get("spec", {}).get("nodeName", ""),
                        })
                return result
    except Exception:
        pass

    # Simulation fallback
    return SIM.get_scheduler_state()


@app.websocket("/api/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            state = {
                "trainer": SIM.get_trainer_state(),
                "workers": {"workers": SIM.get_workers_state()},
                "metrics": {"metrics": SIM.metrics_history},
                "timestamp": time.time(),
            }
            await ws.send_json(state)
            await asyncio.sleep(0.3)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


if __name__ == "__main__":
    import uvicorn
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(os.path.join(DATA_DIR, "monitor"), exist_ok=True)
    port = int(os.environ.get("MONITOR_PORT", "9000"))
    print(f"Starting PPO Training Monitor on port {port}")
    print(f"  DATA_DIR: {DATA_DIR}")
    print(f"  Mode: SIMULATION (auto-switches to LIVE when real training detected)")
    print(f"  Dashboard: http://localhost:{port}/")
    uvicorn.run(app, host="0.0.0.0", port=port)
