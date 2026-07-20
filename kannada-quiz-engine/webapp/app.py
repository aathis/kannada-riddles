"""Web UI for the Kannada Quiz Engine.

Run from the kannada-quiz-engine directory:

    pip install flask
    python webapp/app.py

Then open http://localhost:5001 — fill in the episode form, click Generate,
watch progress, and download the finished MP4 + thumbnail.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory

ROOT = Path(__file__).resolve().parent.parent  # kannada-quiz-engine/
EPISODES = ROOT / "episodes"
OUTPUT = ROOT / "output"

app = Flask(__name__)

# One job at a time keeps this simple; rendering is CPU-heavy anyway.
jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()


def slugify(title_en: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", title_en.lower()).strip("_")
    return slug or "episode"


def unique_episode_id(base: str) -> str:
    ep_id, n = base, 2
    while (EPISODES / f"{ep_id}.json").exists():
        ep_id = f"{base}_{n}"
        n += 1
    return ep_id


def run_generation(ep_id: str) -> None:
    job = jobs[ep_id]
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "src.cli", "generate", f"episodes/{ep_id}.json"],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        for line in proc.stdout:
            job["log"].append(line.rstrip())
        proc.wait()
        job["status"] = "done" if proc.returncode == 0 else "error"
    except Exception as exc:  # surface unexpected failures in the UI
        job["log"].append(str(exc))
        job["status"] = "error"


@app.get("/")
def index():
    return render_template("index.html")


def parse_clue_tokens(raw) -> list[str]:
    """Parse raw clue input into clean tokens, supporting plus '+' separated strings (e.g. 'Geo+📊+y')."""
    if isinstance(raw, list):
        tokens = []
        for item in raw:
            item_str = str(item).strip()
            if "+" in item_str:
                parts = [p.strip() for p in item_str.split("+") if p.strip()]
                tokens.extend(parts)
            elif item_str:
                tokens.append(item_str)
        return tokens

    if isinstance(raw, str):
        raw_str = raw.strip()
        if "+" in raw_str:
            return [p.strip() for p in raw_str.split("+") if p.strip()]
        return [e.strip() for e in re.split(r"[\s,]+", raw_str) if e.strip()]

    return [str(raw)] if raw else []


@app.post("/generate")
def generate():
    data = request.get_json(force=True)

    questions = []
    for i, q in enumerate(data.get("questions", []), start=1):
        raw_emojis = q.get("clue_emojis", "")
        emojis = parse_clue_tokens(raw_emojis)
        questions.append({
            "id": i,
            "clue_emojis": emojis,
            "answer_kn": q.get("answer_kn", "").strip(),
            "answer_en": q.get("answer_en", "").strip(),
            "prompt_text": q.get("prompt_text", "").strip() or "CAN YOU GUESS THE WORD?",
            "narration_kn": q.get("narration_kn", "").strip(),
            "reveal_narration_kn": q.get("reveal_narration_kn", "").strip(),
        })

    title_str = (data.get("title_en") or data.get("title_kn") or "Guess the Word!").strip()
    intro_str = (data.get("intro_narration_kn") or "Welcome to the Word Riddle Quiz! Combine the clues and guess the hidden word.").strip()
    outro_str = (data.get("outro_narration_kn") or "Thanks for playing! How many did you guess correctly? Leave a comment, like, and subscribe for more quiz fun!").strip()

    ep_id = unique_episode_id(slugify(title_str))
    episode = {
        "id": ep_id,
        "title_kn": title_str,
        "title_en": title_str,
        "intro_narration_kn": intro_str,
        "outro_narration_kn": outro_str,
        "bg_music": data.get("bg_music", "soft_piano_gymnopedie"),
        "questions": questions,
    }

    # Validate against the engine's own models before accepting the job.
    sys.path.insert(0, str(ROOT))
    from src.models import Episode  # noqa: PLC0415
    try:
        Episode(**episode)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

    EPISODES.mkdir(exist_ok=True)
    (EPISODES / f"{ep_id}.json").write_text(
        json.dumps(episode, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    with jobs_lock:
        if any(j["status"] == "running" for j in jobs.values()):
            return jsonify({"error": "Another episode is still rendering. Please wait."}), 409
        jobs[ep_id] = {"status": "running", "log": []}

    threading.Thread(target=run_generation, args=(ep_id,), daemon=True).start()
    return jsonify({"episode_id": ep_id})


@app.get("/status/<ep_id>")
def status(ep_id: str):
    job = jobs.get(ep_id)
    if not job:
        return jsonify({"error": "unknown episode"}), 404
    return jsonify({
        "status": job["status"],
        "log": job["log"][-20:],
        "video": f"/output/{ep_id}.mp4" if job["status"] == "done" else None,
        "thumbnail": f"/output/{ep_id}_thumbnail.png" if job["status"] == "done" else None,
    })


MUSIC = ROOT / "music"
LABELS = {
    "soft_piano_gymnopedie": "🎹 Soft & Peaceful Piano (Erik Satie - Gymnopédie No. 1)",
    "calm_moonlight_sonata": "🎼 Calm Classical Piano (Beethoven - Moonlight Sonata)",
    "mellow_gnossienne": "🌙 Mellow & Ambient Piano (Erik Satie - Gnossienne No. 1)",
    "gentle_canon_in_d": "🎻 Gentle Piano & Strings (Pachelbel - Canon in D)",
}


@app.get("/music-list")
def music_list():
    tracks = []
    if MUSIC.exists():
        for f in sorted(MUSIC.glob("*.wav")):
            stem = f.stem
            label = LABELS.get(stem, f"🎵 {stem.replace('_', ' ').title()}")
            tracks.append({"value": stem, "label": label})
    tracks.append({"value": "none", "label": "🔇 None (Voice Narration Only)"})
    return jsonify({"tracks": tracks})


@app.post("/upload-music")
def upload_music():
    if "file" not in request.files:
        return jsonify({"error": "No audio file provided"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Empty file name"}), 400

    filename = slugify(Path(file.filename).stem)
    save_path = MUSIC / f"{filename}.wav"
    tmp_path = MUSIC / f"upload_{file.filename}"
    file.save(tmp_path)

    try:
        from moviepy import AudioFileClip
        clip = AudioFileClip(str(tmp_path))
        clip.write_audiofile(str(save_path), logger=None)
        clip.close()
        if tmp_path.exists():
            tmp_path.unlink()
    except Exception as exc:
        if tmp_path.exists():
            tmp_path.unlink()
        return jsonify({"error": f"Failed to process audio: {exc}"}), 500

    return jsonify({
        "value": filename,
        "label": f"🎵 {filename.replace('_', ' ').title()}"
    })


@app.get("/music/<path:filename>")
def music_file(filename: str):
    return send_from_directory(MUSIC, filename, as_attachment=False)


@app.get("/output/<path:filename>")
def output_file(filename: str):
    return send_from_directory(OUTPUT, filename, as_attachment=False)


if __name__ == "__main__":
    # 5001 by default: macOS AirPlay Receiver occupies 5000.
    import os
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=False)
