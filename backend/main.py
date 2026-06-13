import json
import os
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from flask import Flask, Response, request
from flask_cors import CORS

from ytm import YouTubeAuthExpired, create_ytm_playlist, resume_ytm_playlist

load_dotenv()

JOB_DIR = Path(os.getenv("SPOTTRANSFER_JOB_DIR", tempfile.gettempdir())) / "spottransfer-jobs"
JOB_DIR.mkdir(parents=True, exist_ok=True)

JOB_TTL_SECONDS = int(os.getenv("SPOTTRANSFER_JOB_TTL_SECONDS", "86400"))
JOB_REUSE_SECONDS = int(os.getenv("SPOTTRANSFER_JOB_REUSE_SECONDS", "900"))
executor = ThreadPoolExecutor(max_workers=int(os.getenv("SPOTTRANSFER_JOB_WORKERS", "1")))
jobs_lock = threading.Lock()

app = Flask(__name__)
CORS(
    app,
    resources={
        r"/*": {
            "origins": [os.getenv("FRONTEND_URL", "http://localhost:5173")],
            "methods": ["POST", "GET"],
        }
    },
)


def _job_path(job_id):
    return JOB_DIR / f"{job_id}.json"


def _state_path(job_id):
    return JOB_DIR / f"{job_id}.state"


def _write_job(job_id, payload):
    payload = {
        **payload,
        "job_id": job_id,
        "updated_at": int(time.time()),
    }
    tmp_path = _job_path(f"{job_id}.tmp")
    final_path = _job_path(job_id)
    with jobs_lock:
        tmp_path.write_text(json.dumps(payload), encoding="utf-8")
        tmp_path.replace(final_path)


def _read_job(job_id):
    path = _job_path(job_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_state(job_id, payload):
    tmp_path = _state_path(f"{job_id}.tmp")
    final_path = _state_path(job_id)
    with jobs_lock:
        tmp_path.write_text(json.dumps(payload), encoding="utf-8")
        tmp_path.replace(final_path)


def _read_state(job_id):
    path = _state_path(job_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _delete_state(job_id):
    _state_path(job_id).unlink(missing_ok=True)


def _cleanup_old_jobs():
    cutoff = time.time() - JOB_TTL_SECONDS
    for path in JOB_DIR.glob("*.json"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            app.logger.warning("Failed to clean old job file: %s", path)
    for path in JOB_DIR.glob("*.state"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            app.logger.warning("Failed to clean old job state: %s", path)


def _find_reusable_job(playlist_link):
    now = time.time()
    normalized_link = (playlist_link or "").strip()

    for path in JOB_DIR.glob("*.json"):
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        if job.get("playlist_link") != normalized_link:
            continue

        status = job.get("status")
        if status in {"queued", "running", "needs_auth"}:
            return job

        finished_at = job.get("finished_at")
        if status == "complete" and finished_at and now - finished_at <= JOB_REUSE_SECONDS:
            return job

    return None


def _run_create_job(job_id, playlist_link, auth_headers):
    progress = {}

    def search_progress(found_tracks, processed_tracks, source_tracks):
        progress.update(
            {
                "found_tracks": found_tracks,
                "processed_tracks": processed_tracks,
                "source_tracks": source_tracks,
            }
        )
        _write_job(
            job_id,
            {
                "status": "running",
                "message": (
                    f"Searching songs: {processed_tracks}/{source_tracks} "
                    f"checked, {found_tracks} found"
                ),
                "playlist_link": playlist_link,
                "started_at": started_at,
                **progress,
            },
        )

    def search_complete(resume_state):
        _write_state(job_id, resume_state)
        progress.update(
            {
                "found_tracks": len(resume_state["video_ids"]),
                "source_tracks": resume_state["source_tracks"],
                "unmatched_tracks": resume_state["missed_tracks"]["count"],
                "items_added": resume_state.get("items_added", 0),
                "items_total": len(resume_state["video_ids"]),
                "youtube_playlist_id": resume_state["playlist_id"],
            }
        )
        _write_job(
            job_id,
            {
                "status": "running",
                "message": (
                    f"Found {progress['found_tracks']}/{progress['source_tracks']} "
                    "songs. Adding them to YouTube Music..."
                ),
                "playlist_link": playlist_link,
                "started_at": started_at,
                **progress,
            },
        )

    def update_progress(items_added, items_total, youtube_playlist_id):
        progress.update(
            {
                "items_added": items_added,
                "items_total": items_total,
                "youtube_playlist_id": youtube_playlist_id,
            }
        )
        state = _read_state(job_id)
        if state:
            state["items_added"] = items_added
            _write_state(job_id, state)
        _write_job(
            job_id,
            {
                "status": "running",
                "message": f"Adding songs: {items_added}/{items_total}",
                "playlist_link": playlist_link,
                "started_at": started_at,
                **progress,
            },
        )

    started_at = int(time.time())
    _write_job(
        job_id,
        {
            "status": "running",
            "message": "Cloning playlist...",
            "playlist_link": playlist_link,
            "started_at": started_at,
        },
    )
    try:
        result = create_ytm_playlist(
            playlist_link,
            auth_headers,
            progress_callback=update_progress,
            search_progress_callback=search_progress,
            search_complete_callback=search_complete,
        )
        _delete_state(job_id)
        _write_job(
            job_id,
            {
                "status": "complete",
                "message": "Playlist created successfully!",
                "playlist_link": playlist_link,
                "missed_tracks": result["missed_tracks"],
                "cover_url": result.get("cover_url"),
                "playlist_name": result.get("playlist_name"),
                "has_cover": bool(result.get("cover_url")),
                "found_tracks": result.get("found_tracks"),
                "source_tracks": result.get("source_tracks"),
                **progress,
                "finished_at": int(time.time()),
            },
        )
    except YouTubeAuthExpired as error:
        _write_state(job_id, error.resume_state)
        progress.update(
            {
                "found_tracks": len(error.resume_state["video_ids"]),
                "source_tracks": error.resume_state.get("source_tracks"),
                "unmatched_tracks": error.resume_state["missed_tracks"]["count"],
                "items_added": error.resume_state.get("items_added", 0),
                "items_total": len(error.resume_state["video_ids"]),
                "youtube_playlist_id": error.resume_state["playlist_id"],
            }
        )
        app.logger.warning("YouTube Music auth expired for job %s", job_id)
        _write_job(
            job_id,
            {
                "status": "needs_auth",
                "message": str(error),
                "playlist_link": playlist_link,
                "started_at": started_at,
                **progress,
            },
        )
    except Exception as error:
        app.logger.exception("Failed to create playlist job %s", job_id)
        _write_job(
            job_id,
            {
                "status": "failed",
                "message": str(error),
                "playlist_link": playlist_link,
                **progress,
                "finished_at": int(time.time()),
            },
        )


def _run_resume_job(job_id, playlist_link, auth_headers):
    state = _read_state(job_id)
    if not state:
        _write_job(
            job_id,
            {
                "status": "failed",
                "message": "The saved playlist state is no longer available.",
                "playlist_link": playlist_link,
                "finished_at": int(time.time()),
            },
        )
        return

    started_at = int(time.time())

    def update_progress(items_added, items_total, youtube_playlist_id):
        state["items_added"] = items_added
        _write_state(job_id, state)
        _write_job(
            job_id,
            {
                "status": "running",
                "message": f"Adding songs: {items_added}/{items_total}",
                "playlist_link": playlist_link,
                "started_at": started_at,
                "items_added": items_added,
                "items_total": items_total,
                "youtube_playlist_id": youtube_playlist_id,
                "found_tracks": len(state["video_ids"]),
                "source_tracks": state.get("source_tracks"),
                "unmatched_tracks": state["missed_tracks"]["count"],
            },
        )

    try:
        result = resume_ytm_playlist(
            auth_headers,
            state,
            progress_callback=update_progress,
        )
        _delete_state(job_id)
        _write_job(
            job_id,
            {
                "status": "complete",
                "message": "Playlist created successfully!",
                "playlist_link": playlist_link,
                "missed_tracks": result["missed_tracks"],
                "cover_url": result.get("cover_url"),
                "playlist_name": result.get("playlist_name"),
                "has_cover": bool(result.get("cover_url")),
                "found_tracks": result.get("found_tracks"),
                "source_tracks": result.get("source_tracks"),
                "items_added": len(state["video_ids"]),
                "items_total": len(state["video_ids"]),
                "youtube_playlist_id": state["playlist_id"],
                "finished_at": int(time.time()),
            },
        )
    except YouTubeAuthExpired as error:
        _write_state(job_id, error.resume_state)
        _write_job(
            job_id,
            {
                "status": "needs_auth",
                "message": str(error),
                "playlist_link": playlist_link,
                "items_added": error.resume_state.get("items_added", 0),
                "items_total": len(error.resume_state["video_ids"]),
                "youtube_playlist_id": error.resume_state["playlist_id"],
                "found_tracks": len(error.resume_state["video_ids"]),
                "source_tracks": error.resume_state.get("source_tracks"),
                "unmatched_tracks": error.resume_state["missed_tracks"]["count"],
            },
        )
    except Exception as error:
        app.logger.exception("Failed to resume playlist job %s", job_id)
        _write_job(
            job_id,
            {
                "status": "failed",
                "message": str(error),
                "playlist_link": playlist_link,
                "finished_at": int(time.time()),
            },
        )


@app.route("/create", methods=["POST"])
def create_playlist():
    data = request.get_json(silent=True) or {}
    playlist_link = data.get("playlist_link")
    auth_headers = data.get("auth_headers")

    if not playlist_link:
        return {"message": "Missing playlist_link"}, 400
    if not auth_headers:
        return {"message": "Missing YouTube Music auth headers"}, 400

    _cleanup_old_jobs()
    playlist_link = playlist_link.strip()
    reusable_job = _find_reusable_job(playlist_link)
    if reusable_job:
        app.logger.info(
            "Reusing playlist clone job %s for %s",
            reusable_job["job_id"],
            playlist_link,
        )
        return {
            "message": "Playlist clone already started",
            "job_id": reusable_job["job_id"],
            "status_url": f"/jobs/{reusable_job['job_id']}",
            "reused": True,
        }, 202

    job_id = uuid.uuid4().hex
    _write_job(
        job_id,
        {
            "status": "queued",
            "message": "Playlist clone queued",
            "playlist_link": playlist_link,
            "created_at": int(time.time()),
        },
    )
    app.logger.info("Started playlist clone job %s for %s", job_id, playlist_link)
    executor.submit(_run_create_job, job_id, playlist_link, auth_headers)

    return {
        "message": "Playlist clone started",
        "job_id": job_id,
        "status_url": f"/jobs/{job_id}",
    }, 202


@app.route("/jobs/<job_id>", methods=["GET"])
def get_job(job_id):
    job = _read_job(job_id)
    if not job:
        return {"message": "Job not found"}, 404
    return job, 200


@app.route("/jobs/<job_id>/resume", methods=["POST"])
def resume_playlist(job_id):
    job = _read_job(job_id)
    if not job:
        return {"message": "Job not found"}, 404
    if job.get("status") != "needs_auth":
        return {"message": "This job is not waiting for new headers"}, 409
    if not _read_state(job_id):
        return {"message": "Saved playlist state not found"}, 410

    data = request.get_json(silent=True) or {}
    auth_headers = data.get("auth_headers")
    if not auth_headers:
        return {"message": "Missing YouTube Music auth headers"}, 400

    _write_job(
        job_id,
        {
            **job,
            "status": "queued",
            "message": "Resuming playlist write with fresh headers...",
        },
    )
    executor.submit(
        _run_resume_job,
        job_id,
        job.get("playlist_link", ""),
        auth_headers,
    )
    return {"message": "Playlist write resumed", "job_id": job_id}, 202


def _safe_cover_filename(playlist_name, content_type):
    safe_name = "".join(
        char
        if char.isascii() and (char.isalnum() or char in {" ", "-", "_"})
        else "_"
        for char in (playlist_name or "spotify-playlist")
    ).strip() or "spotify-playlist"
    extension = ".png" if content_type == "image/png" else ".jpg"
    return f'{safe_name[:100]}{extension}'


@app.route("/jobs/<job_id>/cover", methods=["GET"])
def download_playlist_cover(job_id):
    job = _read_job(job_id)
    if not job or job.get("status") != "complete":
        return {"message": "Completed job not found"}, 404

    cover_url = job.get("cover_url")
    parsed_url = urlparse(cover_url or "")
    hostname = (parsed_url.hostname or "").lower()
    if (
        parsed_url.scheme != "https"
        or not hostname
        or not (
            hostname == "scdn.co"
            or hostname.endswith(".scdn.co")
            or hostname == "spotifycdn.com"
            or hostname.endswith(".spotifycdn.com")
        )
    ):
        return {"message": "Spotify playlist cover is unavailable"}, 404

    try:
        cover_response = requests.get(cover_url, timeout=30)
        cover_response.raise_for_status()
    except requests.RequestException:
        app.logger.exception("Failed to download cover for job %s", job_id)
        return {"message": "Failed to download Spotify playlist cover"}, 502

    content_type = cover_response.headers.get("Content-Type", "").split(";", 1)[0]
    if content_type not in {"image/jpeg", "image/png"}:
        return {"message": "Spotify returned an unsupported cover format"}, 502

    filename = _safe_cover_filename(job.get("playlist_name"), content_type)
    return Response(
        cover_response.content,
        mimetype=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.route("/", methods=["GET"])
def home():
    return {"message": "Server Online"}, 200


if __name__ == "__main__":
    app.run(port=8080)
