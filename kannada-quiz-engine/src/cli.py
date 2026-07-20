"""CLI (design doc §6). One command -> complete YouTube-ready episode.

Usage:
    python -m src.cli generate episodes/episode_001.json
"""
from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from .audio.tts import get_tts
from .config_loader import load_settings
from .images.pillow_provider import PillowProvider
from .models import Episode
from .render.renderer import render_episode

app = typer.Typer(add_completion=False)
console = Console()


@app.command()
def validate(episode: Path, config: Path = Path("config/config.yaml")) -> None:
    """Validate episode JSON and config without rendering."""
    load_settings(config)
    ep = Episode(**json.loads(episode.read_text(encoding="utf-8")))
    console.print(f"[green]OK[/green] {ep.id}: {len(ep.questions)} questions valid.")


@app.command()
def generate(episode: Path, config: Path = Path("config/config.yaml")) -> None:
    """Generate a complete episode: images + narration + video + thumbnail."""
    cfg = load_settings(config)
    ep = Episode(**json.loads(episode.read_text(encoding="utf-8")))
    total = len(ep.questions)

    gen_dir = Path(cfg.paths.generated) / ep.id
    img_dir = gen_dir / "images"
    audio_dir = gen_dir / "audio"
    img_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    out_dir = Path(cfg.paths.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    console.rule(f"[bold]{ep.id}[/bold] — {ep.title_en}")

    # 1. Images
    console.print("[cyan]1/4[/cyan] Generating images (Pillow provider)…")
    prov = PillowProvider(cfg)
    prov.intro_card(ep, img_dir / "intro.png")
    for q in ep.questions:
        prov.question_card(q, total, img_dir / f"q{q.id}_clue.png")
        for sec in range(cfg.timing.countdown, 0, -1):
            prov.question_card(q, total, img_dir / f"q{q.id}_count_{sec}.png", countdown=sec)
        prov.reveal_card(q, total, img_dir / f"q{q.id}_reveal.png")
    prov.outro_card(ep, img_dir / "outro.png")

    # 2. Narration
    console.print(f"[cyan]2/4[/cyan] Generating narration ({cfg.tts.provider})…")
    tts = get_tts(cfg)
    if ep.intro_narration_kn and ep.intro_narration_kn.strip():
        tts.synth(ep.intro_narration_kn, audio_dir / "intro")
    for q in ep.questions:
        if q.narration_kn and q.narration_kn.strip():
            tts.synth(q.narration_kn, audio_dir / f"q{q.id}_question")
        if q.reveal_narration_kn and q.reveal_narration_kn.strip():
            tts.synth(q.reveal_narration_kn, audio_dir / f"q{q.id}_reveal")
    if ep.outro_narration_kn and ep.outro_narration_kn.strip():
        tts.synth(ep.outro_narration_kn, audio_dir / "outro")

    # 3. Video
    console.print("[cyan]3/4[/cyan] Rendering video (MoviePy + FFmpeg)…")
    out_mp4 = render_episode(ep, cfg, gen_dir, out_dir / f"{ep.id}.mp4")

    # 4. Thumbnail
    console.print("[cyan]4/4[/cyan] Generating thumbnail…")
    thumb = prov.thumbnail(ep, out_dir / f"{ep.id}_thumbnail.png")

    console.print(f"[bold green]Done![/bold green] Video: {out_mp4}  |  Thumbnail: {thumb}")


if __name__ == "__main__":
    app()
