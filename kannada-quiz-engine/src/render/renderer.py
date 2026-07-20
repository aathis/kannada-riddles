"""Rendering pipeline (design doc §14).

MoviePy 2.x composes the generated images and narration into
a 16:9 H.264 MP4 via FFmpeg.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from moviepy import AudioFileClip, CompositeAudioClip, ImageClip, concatenate_audioclips, concatenate_videoclips

MUSIC_DIR = Path(__file__).resolve().parent.parent.parent / "music"


def _get_ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _tick(path: Path) -> Path:
    """Generate a short countdown tick sound once, via FFmpeg sine."""
    if not path.exists():
        subprocess.run(
            [_get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i",
             "sine=frequency=1050:duration=0.12", "-af", "volume=0.35", str(path)],
            check=True, capture_output=True,
        )
    return path


def _segment(image: Path, audio: Path | None, min_dur: float) -> ImageClip:
    dur = min_dur
    aclip = None
    if audio is not None and audio.exists():
        aclip = AudioFileClip(str(audio))
        dur = max(min_dur, aclip.duration + 0.4)
    clip = ImageClip(str(image), duration=dur)
    if aclip is not None:
        clip = clip.with_audio(aclip)
    return clip


def render_episode(ep: Episode, cfg: Settings, gen_dir: Path, out_file: Path) -> Path:
    t = cfg.timing
    audio_dir = gen_dir / "audio"
    img_dir = gen_dir / "images"
    tick = _tick(gen_dir / "tick.wav")

    clips: list[ImageClip] = [
        _segment(img_dir / "intro.png", audio_dir / "intro.wav", t.intro)
    ]

    for q in ep.questions:
        clips.append(_segment(img_dir / f"q{q.id}_clue.png",
                              audio_dir / f"q{q.id}_question.wav", t.clue))
        for sec in range(t.countdown, 0, -1):
            clips.append(_segment(img_dir / f"q{q.id}_count_{sec}.png", tick, 1.0))
        clips.append(_segment(img_dir / f"q{q.id}_reveal.png",
                              audio_dir / f"q{q.id}_reveal.wav", t.reveal))

    clips.append(_segment(img_dir / "outro.png", audio_dir / "outro.wav", t.outro))

    final = concatenate_videoclips(clips, method="chain")

    # Overlay background music if selected
    bg_music_name = getattr(ep, "bg_music", "soft_piano_gymnopedie") or "soft_piano_gymnopedie"
    if bg_music_name != "none":
        bg_track = MUSIC_DIR / f"{bg_music_name}.wav"
        if bg_track.exists():
            bg_clip = AudioFileClip(str(bg_track))
            repeats = int(final.duration // bg_clip.duration) + 1
            full_bg = (concatenate_audioclips([bg_clip] * repeats)
                       .subclipped(0, final.duration)
                       .with_volume_scaled(0.07))
            if final.audio is not None:
                final = final.with_audio(CompositeAudioClip([final.audio, full_bg]))
            else:
                final = final.with_audio(full_bg)

    out_file.parent.mkdir(parents=True, exist_ok=True)
    final.write_videofile(
        str(out_file), fps=cfg.video.fps, codec="libx264",
        audio_codec="aac", preset="medium", logger=None,
    )
    final.close()
    return out_file
