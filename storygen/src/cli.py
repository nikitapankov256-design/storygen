"""Главная точка входа: storygen make ...

Примеры:
  python3 cli.py make "Как выучить английский за месяц" --out video.mp4
  python3 cli.py make "Секреты продуктивности" --mode local --voice ru-RU-SvetlanaNeural
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from render import build
from story import generate
from tts import DEFAULT_VOICE, synthesize


async def _voice_all(scenes, workdir: str, voice: str) -> None:
    """Озвучить сцены и записать реальную длину каждой в сам объект.

    Важно: после обрезки тишины mp3 становится короче, поэтому длину
    меряем уже по обработанному файлу — иначе картинка не совпадёт с голосом.
    """
    for i, scene in enumerate(scenes, 1):
        path = os.path.join(workdir, f"tts_{i:03d}.mp3")
        result = await synthesize(scene.text, path, voice=voice)
        scene.audio_path = result.path
        scene.duration = result.duration
        print(f"  сцена {i}: {result.duration:.2f}s (попыток: {result.attempts})", flush=True)


def cmd_make(args) -> int:
    os.makedirs(args.workdir, exist_ok=True)

    print(f"[1/4] Сценарий: {args.topic}")
    script = generate(args.topic, mode=args.mode,
                      base_url=args.llm_url, model=args.llm_model,
                      api_key=args.llm_key)
    print(f"  сцен: {len(script.scenes)}")

    print("[2/4] Озвучка...")
    asyncio.run(_voice_all(script.scenes, args.workdir, args.voice))
    script.save(os.path.join(args.workdir, "script.json"))
    print(f"  итого: {script.duration:.2f}s")

    print("[3/4] Рендер...")
    build(script, args.out, args.workdir, with_subtitles=not args.no_subs)

    print(f"[4/4] Готово: {args.out} ({script.duration:.2f}s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="storygen",
        description="Генератор коротких видео из темы: сценарий, озвучка, рендер.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    mk = sub.add_parser("make", help="Собрать видео из темы")
    mk.add_argument("topic", help="Тема видео")
    mk.add_argument("--out", default="result.mp4", help="Выходной файл")
    mk.add_argument("--mode", choices=["local", "llm"], default="local")
    mk.add_argument("--voice", default=DEFAULT_VOICE)
    mk.add_argument("--workdir", default=".work")
    mk.add_argument("--no-subs", action="store_true")
    mk.add_argument("--llm-url", default=os.environ.get("LLM_URL", ""))
    mk.add_argument("--llm-model", default=os.environ.get("LLM_MODEL", ""))
    mk.add_argument("--llm-key", default=os.environ.get("LLM_KEY", ""))

    args = p.parse_args(argv)
    if args.command == "make":
        return cmd_make(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
