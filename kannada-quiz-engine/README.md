# Kannada Quiz Engine

Generates complete YouTube-ready Kannada rebus quiz videos (16:9, 1920x1080)
from a single command. Based on the Software Design Document v1.0.

One command produces: episode video (MP4), thumbnail (PNG), all clue/answer
images, and Kannada narration.

## Quick start

```bash
# 1. Install system tools (Ubuntu/Debian; on Mac use: brew install ffmpeg espeak-ng)
sudo apt install ffmpeg espeak-ng fonts-noto-core fonts-noto-color-emoji

# 2. Install Python packages (Python 3.12+)
pip install -r requirements.txt

# 3. Generate an episode
python -m src.cli generate episodes/episode_001.json
```

Output appears in `output/episode_001.mp4` and `output/episode_001_thumbnail.png`.

## Natural voice (recommended on your machine)

The default TTS is espeak-ng (offline, robotic). For a natural neural Kannada
voice, edit `config/config.yaml`:

```yaml
tts:
  provider: edge        # was: espeak
```

`edge-tts` is already in requirements.txt and needs internet. Voice options:
`kn-IN-SapnaNeural` (female) or `kn-IN-GaganNeural` (male).

## Web UI (no JSON editing needed)

```bash
python webapp/app.py
```

Open http://localhost:5001 — fill in the episode form (titles, narrations,
add/remove questions), click **Generate video**, watch progress, then preview
and download the MP4 + thumbnail from the page. Episode JSON files are saved
to `episodes/` automatically.

## Rendering on GitHub (no local machine needed)

The workflow `.github/workflows/render-episode.yml` renders episodes on
GitHub's servers: push a new/changed JSON file in `episodes/` (or run the
workflow manually from the Actions tab, giving it an episode path) and
download the finished video + thumbnail from the workflow run's artifacts.

## Creating new episodes

Copy `episodes/episode_001.json`, change the questions, run generate.
Each question needs: `clue_emojis`, `answer_kn`, `answer_en`, `narration_kn`,
`reveal_narration_kn`. The JSON is the single source of truth — no code changes
needed for new content.

Validate before rendering:

```bash
python -m src.cli validate episodes/my_episode.json
```

## Customization (no code changes)

Everything visual/timing lives in `config/config.yaml`:
resolution, fps, segment durations, colors, fonts, channel branding, TTS voice.

## Architecture (matches design doc)

```
src/
  models.py            # Pydantic models — typed JSON contract (§10)
  config_loader.py     # YAML settings (§15)
  images/              # PillowProvider (§13) — swap for an AI provider later
  audio/               # TTS providers: espeak / edge-tts (§12)
  render/              # MoviePy + FFmpeg pipeline (§14)
  cli.py               # Typer CLI (§6)
episodes/              # Episode JSON files (source of truth)
generated/             # Intermediate images + audio (reproducible)
output/                # Final MP4 + thumbnail
```

To plug in an AI image service later, add a class next to `PillowProvider`
with the same methods (`intro_card`, `question_card`, `reveal_card`,
`outro_card`, `thumbnail`) — the renderer needs no changes.

## Note for Claude Code

If you are Claude Code setting this up: install the system dependencies above,
run `pip install -r requirements.txt`, switch `tts.provider` to `edge`,
run the generate command, and verify `output/episode_001.mp4` plays with audio.
On non-Linux systems, update the font paths in `config/config.yaml` to local
Noto Sans Kannada / Noto Color Emoji font locations.
