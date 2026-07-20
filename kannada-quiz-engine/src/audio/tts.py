"""TTS providers (design doc §12).

- EspeakKannadaTTS: fully offline, works anywhere. Robotic but reliable.
- EdgeTTS: natural Microsoft neural Kannada voice. Needs internet.
Switch via config: tts.provider = espeak | edge
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from ..config_loader import Settings


class TTSProvider:
    def synth(self, text: str, out: Path) -> Path:  # pragma: no cover - interface
        raise NotImplementedError


class EspeakKannadaTTS(TTSProvider):
    def __init__(self, cfg: Settings):
        self.cfg = cfg

    def synth(self, text: str, out: Path) -> Path:
        out = out.with_suffix(".wav")
        raw = out.with_suffix(".raw.wav")
        t = self.cfg.tts
        subprocess.run(
            ["espeak-ng", "-v", "kn",
             "-s", str(t.espeak_speed),
             "-a", str(t.espeak_amplitude),
             "-p", str(t.espeak_pitch),
             "-g", str(t.espeak_word_gap),
             "-w", str(raw), text],
            check=True, capture_output=True,
        )
        if t.espeak_soften:
            # Soften metallic highs, remove rumble, gentle level smoothing.
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(raw), "-af",
                 "highpass=f=90,lowpass=f=4600,"
                 "acompressor=threshold=-18dB:ratio=2.5:attack=8:release=120,"
                 "volume=1.15",
                 str(out)],
                check=True, capture_output=True,
            )
            raw.unlink(missing_ok=True)
        else:
            raw.rename(out)
        return out


class EdgeTTS(TTSProvider):
    """Natural voice. `pip install edge-tts` and internet required."""

    def __init__(self, cfg: Settings):
        self.cfg = cfg

    def synth(self, text: str, out: Path) -> Path:
        import asyncio

        import edge_tts  # type: ignore

        out = out.with_suffix(".mp3")

        async def _run() -> None:
            await edge_tts.Communicate(text, self.cfg.tts.edge_voice).save(str(out))

        asyncio.run(_run())
        return out


def get_tts(cfg: Settings) -> TTSProvider:
    if cfg.tts.provider == "edge":
        return EdgeTTS(cfg)
    return EspeakKannadaTTS(cfg)
