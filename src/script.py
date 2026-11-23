"""Модель сценария и приведение его к таймингам озвучки.

Сценарий — это список сцен. У каждой сцены есть текст, который уходит
в TTS, и визуальное описание: фон, заголовок, подпись и тип анимации.
Длительность сцены не задаётся вручную — она измеряется по реальной
длине озвучки, поэтому картинка и голос не разъезжаются.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Literal

Animation = Literal["fade", "slide", "zoom", "none"]


@dataclass
class Scene:
    text: str                 # что произносит диктор
    heading: str = ""         # крупный заголовок в кадре
    caption: str = ""         # подпись под заголовком
    background: str = "0x101018"
    accent: str = "0x9be15d"
    animation: Animation = "fade"
    # заполняется на этапе сборки
    audio_path: str = ""
    duration: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Script:
    title: str
    scenes: list[Scene] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return round(sum(s.duration for s in self.scenes), 3)

    def to_dict(self) -> dict:
        return {"title": self.title, "duration": self.duration,
                "scenes": [s.to_dict() for s in self.scenes]}

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> "Script":
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        scenes = [Scene(**s) for s in raw.get("scenes", [])]
        return cls(title=raw.get("title", "Без названия"), scenes=scenes)
