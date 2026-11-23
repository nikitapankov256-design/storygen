"""Полный конвейер с устойчивостью к обрывам.

TTS к сервису Microsoft на мобильном канале рвётся часто, поэтому:
  1) уже озвученные сцены не переозвучиваются (берутся из кэша),
  2) каждая сцена пишет свой статус в лог сразу,
  3) готовый script.json с длительностями сохраняется до рендера.
"""
import asyncio, json, os, sys
from story import local_script
from tts import synthesize
from render import build

WORK = sys.argv[1] if len(sys.argv) > 1 else ".run"
OUT = sys.argv[2] if len(sys.argv) > 2 else "out.mp4"
TOPIC = sys.argv[3] if len(sys.argv) > 3 else "Как перестать откладывать дела"

os.makedirs(WORK, exist_ok=True)

async def voice(sc):
    for i, scene in enumerate(sc.scenes, 1):
        path = os.path.join(WORK, f"tts_{i:03d}.mp3")
        if os.path.exists(path) and os.path.getsize(path) > 1200:
            from probe import audio_duration
            scene.audio_path = os.path.abspath(path)
            scene.duration = audio_duration(path)
            print(f"  сцена {i}: из кэша {scene.duration:.2f}s", flush=True)
            continue
        r = await synthesize(scene.text, path)
        scene.audio_path = os.path.abspath(r.path)
        scene.duration = r.duration
        print(f"  сцена {i}: {r.duration:.2f}s попыток={r.attempts}", flush=True)
        sc.save(os.path.join(WORK, "script.json"))

def main():
    print(f"ТЕМА: {TOPIC}", flush=True)
    sc = local_script(TOPIC)
    asyncio.run(voice(sc))
    sc.save(os.path.join(WORK, "script.json"))
    print(f"озвучено: {sc.duration:.2f}s", flush=True)
    print("рендер...", flush=True)
    build(sc, OUT, WORK, with_subtitles=True)
    print(f"ГОТОВО: {OUT}", flush=True)

main()
