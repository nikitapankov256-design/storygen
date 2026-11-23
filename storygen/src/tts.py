"""TTS через edge-tts с надёжными ретраями.

edge-tts использует WebSocket к Microsoft. На мобильном канале соединение
часто рвётся, поэтому каждая фраза синтезируется с несколькими попытками
и подтверждается по размеру файла, а не по отсутствию исключения.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
from dataclasses import dataclass

import edge_tts

DEFAULT_VOICE = "ru-RU-DmitryNeural"
MIN_BYTES = 1200


@dataclass
class TtsResult:
    text: str
    path: str
    duration: float
    attempts: int


async def _stream_to_file(text: str, path: str, voice: str, rate: str) -> bool:
    """Пишем аудио потоком: метод .save() теряет данные на длинных фразах."""
    data = bytearray()
    try:
        async for chunk in edge_tts.Communicate(text, voice, rate=rate).stream():
            if chunk["type"] == "audio":
                data += chunk["data"]
    except Exception:
        return False
    if len(data) < MIN_BYTES:
        return False
    with open(path, "wb") as fh:
        fh.write(data)
    return True


def _measured(path: str) -> float:
    from probe import audio_duration
    return audio_duration(path)


def _trim_silence(path: str) -> str:
    """Убрать тишину по краям фразы.

    edge-tts добавляет ~0.5-1.2 с тишины в начале и конце каждого чанка.
    При склейке нескольких сцен это даёт рваный ритм с провалами, поэтому
    паузы срезаем, а кадры сцен подгоняем уже под чистую длину речи.
    """
    out = path.replace(".mp3", "_trim.mp3")
    filt = (
        "silenceremove=start_periods=1:start_duration=0:start_threshold=-45dB,"
        "areverse,"
        "silenceremove=start_periods=1:start_duration=0:start_threshold=-45dB,"
        "areverse"
    )
    res = subprocess.run(
        ["ffmpeg", "-hide_banner", "-v", "error", "-i", path,
         "-af", filt, "-y", out],
        capture_output=True, text=True,
    )
    if res.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) < MIN_BYTES:
        return path
    return out


async def synthesize(
    text: str,
    path: str,
    voice: str = DEFAULT_VOICE,
    rate: str = "+0%",
    retries: int = 5,
) -> TtsResult:
    """Синтезировать фразу. Возвращает результат с числом попыток.

    Ретраи обязательны: на этом канале примерно каждый четвёртый запрос
    к сервису обрывается, и без повтора озвучка теряет куски текста.
    """
    if os.path.exists(path) and os.path.getsize(path) > MIN_BYTES:
        return TtsResult(text, path, _measured(path), 0)

    for attempt in range(1, retries + 1):
        if await _stream_to_file(text, path, voice, rate):
            trimmed = _trim_silence(path)
            return TtsResult(text, trimmed, _measured(trimmed), attempt)
        await asyncio.sleep(1.2 * attempt)
    raise RuntimeError(f"TTS не удался после {retries} попыток: {text[:40]!r}")
