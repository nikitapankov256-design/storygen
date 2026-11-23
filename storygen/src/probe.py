"""Обёртки над ffprobe для длительности и параметров медиа."""
from __future__ import annotations

import json
import subprocess


def _ffprobe_json(path: str, *args: str) -> dict:
    cmd = ["ffprobe", "-v", "error", "-print_format", "json", *args, path]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(out.stdout or "{}")


def audio_duration(path: str) -> float:
    info = _ffprobe_json(path, "-show_entries", "format=duration")
    try:
        return float(info["format"]["duration"])
    except (KeyError, ValueError):
        return 0.0


def video_size(path: str) -> tuple[int, int]:
    info = _ffprobe_json(path, "-show_entries", "stream=width,height", "-select_streams", "v:0")
    try:
        s = info["streams"][0]
        return int(s["width"]), int(s["height"])
    except (KeyError, IndexError):
        return 0, 0
