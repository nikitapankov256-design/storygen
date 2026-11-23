"""Рендер сцен и сборка финального ролика через ffmpeg.

Каждая сцена рендерится отдельным clippiece в 1:1 с её озвучкой,
затем片段 склеиваются, накладывается закадровый голос и (опционально)
титры. Такой подход не требует ни GPU, ни MoviePy — только ffmpeg.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

WIDTH, HEIGHT, FPS = 1080, 1920, 30
FONT_PATH = os.path.join(os.environ.get("PREFIX", "/usr"), "share/fonts/TTF/DejaVuSans-Bold.ttf")


def _fontconfig_env() -> dict:
    """fontconfig в Termux не подхватывает конфиг сам — указываем явно.

    Без этого libass (фильтр subtitles) и drawtext падают с
    "Cannot load default config file" и не находят шрифты.
    """
    env = dict(os.environ)
    cfg = os.path.join(os.environ.get("PREFIX", "/usr"), "etc", "fonts", "fonts.conf")
    if os.path.exists(cfg):
        env["FONTCONFIG_FILE"] = cfg
        env.setdefault("FONTCONFIG_PATH", os.path.dirname(cfg))
    return env


def _run(cmd: list[str], what: str = "") -> None:
    res = subprocess.run(cmd, capture_output=True, text=True, env=_fontconfig_env())
    if res.returncode != 0:
        tail = (res.stderr or "")[-600:]
        raise RuntimeError(f"ffmpeg не смог {what or 'выполнить шаг'}:\n{tail}")


def _has_font() -> str:
    if not os.path.exists(FONT_PATH):
        raise RuntimeError(
            f"Шрифт не найден: {FONT_PATH}. Установи пакет ttf-dejavu."
        )
    return FONT_PATH


def _esc(text: str) -> str:
    """Экранируем текст для drawtext: двоеточия и кавычки ломают фильтр."""
    return (text.replace("\\", "\\\\").replace(":", "\\:")
                .replace("'", "’").replace("%", "\\%"))


def render_scene(scene, index: int, workdir: str) -> str:
    """Отрисовать одну сцену с анимацией. Возвращает путь к mp4-фрагменту.

    Анимация:
      fade  — плавное проявление текста (alpha по t),
      slide — выезд текста снизу,
      zoom  — наезд камеры через zoompan.

    Все выражения опираются на t (время внутри сцены), поэтому движение
    всегда укладывается в длину озвучки этой сцены.
    """
    font = _has_font()
    dur = max(scene.duration, 0.8)
    out = os.path.join(workdir, f"scene_{index:03d}.mp4")
    anim = scene.animation or "fade"

    layers = [f"drawbox=x=0:y=ih-14:w=iw:h=14:color={scene.accent}@0.9:t=fill"]
    layers.append(_text_layer(font, scene, anim, dur))

    pre = ""
    if anim == "zoom":
        # zoompan: z растёт от 1.0 к 1.08 за длину сцены
        frames = max(int(dur * FPS), 1)
        step = 0.08 / frames
        pre = f"zoompan=z='min(1+{step:.6f}*on,1.08)':d=1:s={WIDTH}x{HEIGHT}:fps={FPS},"

    vf = pre + ",".join(layers)

    _run([
        "ffmpeg", "-hide_banner", "-v", "error",
        "-f", "lavfi", "-i",
        f"color=c={scene.background}:s={WIDTH}x{HEIGHT}:d={dur:.3f}:r={FPS}",
        "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", out,
    ], f"рендер сцены {index}")
    return out


def _text_layer(font: str, scene, anim: str, dur: float) -> str:
    """drawtext для заголовка и подписи с анимацией появления."""
    parts = []
    base_y = 780

    # В drawtext запятые внутри выражения нужно экранировать: иначе ffmpeg
    # считает их разделителями опций фильтра.
    if anim == "slide":
        y = f"if(lt(t\\,0.5)\\,{base_y}+200*(1-t/0.5)\\,{base_y})"
        alpha = "1"
    elif anim == "fade":
        y = f"{base_y}"
        alpha = f"if(lt(t\\,0.6)\\,t/0.6\\,1)"
    else:  # zoom
        y = f"{base_y}"
        alpha = f"if(lt(t\\,0.5)\\,t/0.5\\,1)"

    if scene.heading:
        parts.append(
            f"drawtext=fontfile={font}:text='{_esc(scene.heading)}':"
            f"fontcolor=white:fontsize=76:x=(w-text_w)/2:y={y}:alpha='{alpha}'"
        )
    if scene.caption:
        parts.append(
            f"drawtext=fontfile={font}:text='{_esc(scene.caption)}':"
            f"fontcolor={scene.accent}:fontsize=48:"
            f"x=(w-text_w)/2:y={base_y + 150}:alpha='{alpha}'"
        )
    return ",".join(parts)


def build(script, out_path: str, workdir: str, with_subtitles: bool = True) -> str:
    """Собрать финальный ролик из сценария."""
    if not script.scenes:
        raise RuntimeError("В сценарии нет сцен")

    seg_paths = []
    for i, scene in enumerate(script.scenes, 1):
        seg_paths.append(render_scene(scene, i, workdir))

    concat_list = os.path.join(workdir, "concat.txt")
    with open(concat_list, "w", encoding="utf-8") as fh:
        for p in seg_paths:
            fh.write(f"file '{os.path.abspath(p)}'\n")

    video_only = os.path.join(workdir, "_video.mp4")
    _run([
        "ffmpeg", "-hide_banner", "-v", "error",
        "-f", "concat", "-safe", "0", "-i", concat_list,
        "-c", "copy", "-y", video_only,
    ], "склейка сцен")

    audio_inputs: list[str] = []
    for scene in script.scenes:
        audio_inputs += ["-i", scene.audio_path]

    # Вход 0 — склеенное видео (без звука), входы 1..n — озвучка сцен.
    # Нормализация громкости встроена в filter_complex: --af нельзя применять
    # к потоку, который уже является выходом сложного фильтра.
    n = len(script.scenes)
    filt = "".join(f"[{i}:a]" for i in range(1, n + 1)) + (
        f"concat=n={n}:v=0:a=1,"
        "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=44100[aout]"
    )

    cmd = ["ffmpeg", "-hide_banner", "-v", "error", "-i", video_only]
    cmd += audio_inputs
    # -af нормализует громкость: edge-tts отдаёт звук заметно тише, чем
    # музыка в типичном ролике, и на телефоне такую озвучку почти не слышно.
    cmd += ["-filter_complex", filt, "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-shortest"]

    if with_subtitles:
        srt = os.path.join(workdir, "subs.srt")
        _write_srt(script, srt)
        cmd += ["-vf", f"subtitles={srt}:force_style='FontName=DejaVu Sans,FontSize=22,Outline=2'"]
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]

    cmd += ["-movflags", "+faststart", "-y", out_path]
    _run(cmd, "сборка финального ролика")
    return out_path


def _ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def _write_srt(script, path: str) -> None:
    """Титры по одной строке на сцену, тайминги берём из озвучки."""
    t = 0.0
    blocks = []
    for i, scene in enumerate(script.scenes, 1):
        start, end = t, t + scene.duration
        blocks.append(f"{i}\n{_ts(start)} --> {_ts(end)}\n{scene.text}\n")
        t = end
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(blocks))
