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


@app.post("/generate")
def generate():
    data = request.get_json(force=True)

    questions = []
    for i, q in enumerate(data.get("questions", []), start=1):
        emojis = [e for e in re.split(r"[\s,]+", q.get("clue_emojis", "").strip()) if e]
        questions.append({
            "id": i,
            "clue_emojis": emojis,
            "answer_kn": q.get("answer_kn", "").strip(),
            "answer_en": q.get("answer_en", "").strip(),
            "narration_kn": q.get("narration_kn", "").strip(),
            "reveal_narration_kn": q.get("reveal_narration_kn", "").strip(),
        })

    ep_id = unique_episode_id(slugify(data.get("title_en", "")))
    episode = {
        "id": ep_id,
        "title_kn": data.get("title_kn", "").strip(),
        "title_en": data.get("title_en", "").strip(),
        "intro_narration_kn": data.get("intro_narration_kn", "").strip(),
        "outro_narration_kn": data.get("outro_narration_kn", "").strip(),
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


@app.get("/output/<path:filename>")
def output_file(filename: str):
    return send_from_directory(OUTPUT, filename, as_attachment=False)


if __name__ == "__main__":
    # 5001 by default: macOS AirPlay Receiver occupies 5000.
    import os
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=False)
