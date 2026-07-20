"""Load YAML config into typed settings (design doc §15)."""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel


class VideoCfg(BaseModel):
    width: int
    height: int
    fps: int


class TimingCfg(BaseModel):
    intro: float
    clue: float
    countdown: int
    reveal: float
    outro: float


class ColorsCfg(BaseModel):
    bg_top: str
    bg_bottom: str
    reveal_top: str
    reveal_bottom: str
    accent: str
    text: str
    subtext: str
    timer_ring: str


class FontsCfg(BaseModel):
    kannada_regular: str
    kannada_bold: str
    latin_bold: str
    emoji: str


class BrandingCfg(BaseModel):
    channel_name_kn: str
    channel_name_en: str


class TTSCfg(BaseModel):
    provider: str = "espeak"
    edge_voice: str = "kn-IN-SapnaNeural"
    espeak_speed: int = 140
    espeak_amplitude: int = 180
    espeak_pitch: int = 50
    espeak_word_gap: int = 0
    espeak_soften: bool = True


class PathsCfg(BaseModel):
    generated: str = "generated"
    output: str = "output"


class Settings(BaseModel):
    video: VideoCfg
    timing: TimingCfg
    colors: ColorsCfg
    fonts: FontsCfg
    branding: BrandingCfg
    tts: TTSCfg
    paths: PathsCfg


def load_settings(path: str | Path) -> Settings:
    with open(path, "r", encoding="utf-8") as f:
        return Settings(**yaml.safe_load(f))
