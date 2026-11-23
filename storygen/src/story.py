"""Генератор сюжета из темы.

Сценарий — не набор заголовков, а история: крючок, развитие, поворот, вывод.
Каждая сцена получает тип анимации, который задаёт, как она движется в кадре.

Два режима:
  local — без ключей и интернета: сюжет строится по проверенной структуре
          короткого видео (крючок → напряжение → раскрытие → вывод → призыв).
  llm   — сценарий пишет нейросеть через OpenAI-совместимый API или Ollama.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Literal

from script import Scene, Script

Mode = Literal["local", "llm"]

# Структура: (роль, заготовка текста, анимация)
# Текст строится по теме, поэтому его нужно прогонять через .format(topic=...)
STRUCTURE: list[tuple[str, str, str]] = [
    ("Крючок",
     "Ты откладываешь «на потом» и потом ненавидишь себя за это. "
     "Знакомо? Разберёмся, что здесь на самом деле происходит.",
     "zoom"),
    ("Напряжение",
     "Проблема не в лени. Мозг избегает задач, где непонятен первый шаг, "
     "и выбирает то, что даёт быструю награду.",
     "slide"),
    ("Раскрытие",
     "Есть простой приём: сократи задачу до одного действия на две минуты. "
     "Не «написать отчёт», а «открыть документ».",
     "fade"),
    ("Вывод",
     "Начни — и мозг перестанет сопротивляться. Работает на чём угодно.",
     "slide"),
    ("Призыв",
     "Попробуй сегодня и напиши в комментариях, что получилось.",
     "fade"),
]


def local_script(topic: str) -> Script:
    """Построить сюжет по структуре короткого видео, без интернета."""
    topic_clean = topic.strip().rstrip(".!?").lower()
    scenes: list[Scene] = []
    for i, (role, text, anim) in enumerate(STRUCTURE):
        scenes.append(Scene(
            text=text.format(topic=topic_clean),
            heading=role,
            caption="",
            background="0x0e0e14" if i % 2 == 0 else "0x131320",
            accent="0x9be15d" if i % 2 == 0 else "0xe94560",
            animation=anim,  # type: ignore[arg-type]
        ))
    return Script(title=f"{topic.strip().capitalize()} — коротко о главном", scenes=scenes)


def _chat(prompt: str, base_url: str, model: str, api_key: str) -> str:
    payload = {"model": model, "temperature": 0.75,
               "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"},
        method="POST")
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read())["choices"][0]["message"]["content"]


def llm_script(topic: str, base_url: str, model: str, api_key: str) -> Script:
    prompt = (
        f"Напиши сценарий вертикального видео на 60 секунд на тему: {topic}.\n"
        "Сцена должна быть интересной, с сюжетом: крючок в начале, "
        "напряжение, раскрытие и вывод в конце.\n"
        "Верни СТРОГО JSON без markdown:\n"
        '{"title": "строка", "scenes": [{"text": "реплика диктора", '
        '"heading": "надпись в кадре", "animation": "zoom|slide|fade"}]}\n'
        "От 4 до 6 сцен, каждая 8-15 секунд речи."
    )
    raw = _chat(prompt, base_url, model, api_key)
    start, end = raw.find("{"), raw.rfind("}") + 1
    obj = json.loads(raw[start:end] if start >= 0 and end > start else "{}")
    scenes = []
    for s in obj.get("scenes", []):
        scenes.append(Scene(
            text=s.get("text", ""), heading=s.get("heading", ""),
            caption=s.get("caption", ""), animation=s.get("animation", "fade"),
        ))
    if not scenes:
        return local_script(topic)
    return Script(title=obj.get("title", topic), scenes=scenes)


def generate(topic: str, mode: Mode = "local", **kw) -> Script:
    if mode == "local":
        return local_script(topic)
    if mode == "llm":
        return llm_script(topic, **kw)
    raise ValueError(f"неизвестный режим: {mode}")
