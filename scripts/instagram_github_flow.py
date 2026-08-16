#!/usr/bin/env python3
"""Prepare and publish Instagram Reels from a GitHub Actions queue.

The queue is deliberately small and human-readable. Videos are not committed to
the repository: the prepared MP4 is uploaded to a public GitHub Release so that
Instagram can fetch it without the runner or the user's computer being online.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests


ROOT = Path(__file__).resolve().parents[1]
QUEUE_FILE = ROOT / "queue.json"
WORK_DIR = ROOT / ".work"
LOCAL_TZ = ZoneInfo("Europe/Lisbon")
SLOT_HOURS = (12, 17, 22)
CAPTION = "RATE THIS 🔥"
INSTAGRAM_USER_ID = os.environ.get("INSTAGRAM_USER_ID", "28527008726917037")
INSTAGRAM_API = os.environ.get("INSTAGRAM_API_BASE", "https://graph.instagram.com/v25.0")
GITHUB_API = "https://api.github.com"


def now_local() -> datetime:
    return datetime.now(timezone.utc).astimezone(LOCAL_TZ)


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=LOCAL_TZ)
        return parsed.astimezone(LOCAL_TZ)
    except ValueError:
        return None


def iso(value: datetime) -> str:
    return value.astimezone(LOCAL_TZ).replace(microsecond=0).isoformat()


def load_queue() -> list[dict[str, Any]]:
    if not QUEUE_FILE.exists():
        return []
    with QUEUE_FILE.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict):
        data = data.get("items", [])
    if not isinstance(data, list):
        raise ValueError("queue.json deve conter uma lista de itens")
    return data


def save_queue(items: list[dict[str, Any]]) -> None:
    with QUEUE_FILE.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(items, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def slugify(value: str, max_len: int = 70) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    normalized = re.sub(r"[^A-Za-z0-9]+", "-", normalized).strip("-").lower()
    return (normalized or "video")[:max_len].strip("-")


def item_id(item: dict[str, Any]) -> str:
    if item.get("id"):
        return str(item["id"])
    seed = f"{item.get('title', '')}-{item.get('url', '')}"
    return slugify(seed, 48)


def choose_next_slot(items: list[dict[str, Any]], current: datetime | None = None) -> datetime:
    """Return the next free Lisbon slot, never exceeding 3 slots per day."""
    current = current or now_local()
    occupied: set[tuple[date, int]] = set()
    for item in items:
        scheduled = parse_dt(item.get("scheduled_at"))
        if scheduled:
            occupied.add((scheduled.date(), scheduled.hour))

    for day_offset in range(0, 90):
        candidate_date = current.date() + timedelta(days=day_offset)
        for hour in SLOT_HOURS:
            candidate = datetime.combine(candidate_date, dt_time(hour), tzinfo=LOCAL_TZ)
            if candidate <= current:
                continue
            if (candidate_date, hour) not in occupied:
                return candidate
    raise RuntimeError("Não foi possível encontrar um horário livre nos próximos 90 dias")


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, check=True)


def video_dimensions(path: Path) -> tuple[int, int]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    streams = json.loads(result.stdout).get("streams", [])
    if not streams:
        raise RuntimeError(f"Não foi encontrada imagem de vídeo em {path.name}")
    return int(streams[0]["width"]), int(streams[0]["height"])


def download_and_convert(item: dict[str, Any], destination: Path) -> Path:
    source_dir = WORK_DIR / f"source-{slugify(item_id(item), 45)}"
    if source_dir.exists():
        shutil.rmtree(source_dir)
    source_dir.mkdir(parents=True, exist_ok=True)

    source_template = str(source_dir / "source.%(ext)s")
    run(
        [
            "yt-dlp",
            "--no-playlist",
            "--retries",
            "5",
            "--fragment-retries",
            "5",
            "--concurrent-fragments",
            "8",
            "-f",
            "bv*+ba/b",
            "--format-sort",
            "res,fps,tbr",
            "--merge-output-format",
            "mp4",
            "--extractor-args",
            "youtube:player_client=android_vr,web_safari",
            "-o",
            source_template,
            str(item["url"]),
        ]
    )

    sources = sorted(
        p for p in source_dir.iterdir() if p.is_file() and p.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov", ".m4v"}
    )
    if not sources:
        raise RuntimeError("yt-dlp terminou sem criar um ficheiro de vídeo")
    source = sources[0]
    width, height = video_dimensions(source)
    # Horizontal source clips are rotated 90 degrees to the right, matching the
    # established channel workflow. Vertical and square clips are not rotated.
    rotate = "transpose=1," if width > height else ""
    filter_chain = (
        f"{rotate}scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,"
        "crop=1080:1920,setsar=1"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-vf",
            filter_chain,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            "-shortest",
            str(destination),
        ]
    )
    shutil.rmtree(source_dir, ignore_errors=True)
    return destination


def github_headers(token: str, content_type: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def create_release_and_upload(item: dict[str, Any], video_path: Path) -> tuple[str, str]:
    token = os.environ.get("GITHUB_TOKEN")
    repository = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repository:
        raise RuntimeError("GITHUB_TOKEN/GITHUB_REPOSITORY não estão disponíveis no Actions")
    if video_path.stat().st_size >= 2 * 1024 * 1024 * 1024:
        raise RuntimeError("O vídeo excede o limite de 2 GiB de um asset de Release")

    release_tag = f"ig-{slugify(item_id(item), 42)}-{int(time.time())}"
    release_response = requests.post(
        f"{GITHUB_API}/repos/{repository}/releases",
        headers=github_headers(token, "application/json"),
        json={
            "tag_name": release_tag,
            "name": f"Instagram — {item.get('title', item_id(item))}",
            "body": "Asset temporário para publicação automática no Instagram.",
            "draft": False,
            "prerelease": False,
        },
        timeout=60,
    )
    release_response.raise_for_status()
    release = release_response.json()
    asset_name = f"{slugify(item.get('title', item_id(item)), 70)}.mp4"
    upload_url = release["upload_url"].split("{", 1)[0]
    with video_path.open("rb") as video_handle:
        upload_response = requests.post(
            upload_url,
            params={"name": asset_name},
            headers=github_headers(token, "video/mp4"),
            data=video_handle,
            timeout=1800,
        )
    upload_response.raise_for_status()
    asset = upload_response.json()
    return str(asset["browser_download_url"]), release_tag


def instagram_request(method: str, path: str, token: str, **kwargs: Any) -> dict[str, Any]:
    params = kwargs.pop("params", {})
    params["access_token"] = token
    response = requests.request(method, f"{INSTAGRAM_API}/{path.lstrip('/')}", params=params, timeout=60, **kwargs)
    if not response.ok:
        raise RuntimeError(f"Instagram API {response.status_code}: {response.text[:800]}")
    return response.json()


def publish_reel(video_url: str, caption: str, token: str) -> dict[str, Any]:
    container = instagram_request(
        "POST",
        f"/{INSTAGRAM_USER_ID}/media",
        token,
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": "true",
        },
    )
    creation_id = container["id"]
    deadline = time.time() + 15 * 60
    while time.time() < deadline:
        status = instagram_request(
            "GET",
            f"/{creation_id}",
            token,
            params={"fields": "status_code,status"},
        )
        status_code = status.get("status_code")
        if status_code == "FINISHED":
            break
        if status_code in {"ERROR", "EXPIRED"}:
            raise RuntimeError(f"Instagram container {creation_id} terminou com {status}")
        time.sleep(15)
    else:
        raise TimeoutError(f"Instagram não processou o container {creation_id} em 15 minutos")

    published = instagram_request(
        "POST",
        f"/{INSTAGRAM_USER_ID}/media_publish",
        token,
        data={"creation_id": creation_id},
    )
    media_id = published["id"]
    return instagram_request(
        "GET",
        f"/{media_id}",
        token,
        params={"fields": "id,permalink,caption,media_product_type"},
    )


def prepare_pending(items: list[dict[str, Any]]) -> None:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    for item in items:
        if item.get("status", "pending") != "pending":
            continue
        if not item.get("url"):
            item["status"] = "failed"
            item["last_error"] = "Item sem URL"
            continue
        # A manually supplied future time is used for one-off tests. Normal
        # queue items leave scheduled_at null and receive the next 12/17/22 slot.
        scheduled = parse_dt(item.get("scheduled_at")) or choose_next_slot(items)
        item["id"] = item_id(item)
        item["title"] = item.get("title") or item["id"]
        item["caption"] = CAPTION
        item["scheduled_at"] = iso(scheduled)
        item["status"] = "preparing"
        item.pop("last_error", None)
        print(f"A preparar {item['title']} para {item['scheduled_at']}", flush=True)
        try:
            output = WORK_DIR / f"{slugify(item['title'])}.mp4"
            download_and_convert(item, output)
            public_url, release_tag = create_release_and_upload(item, output)
            item["release_tag"] = release_tag
            item["video_url"] = public_url
            item["status"] = "ready"
            item["prepared_at"] = iso(now_local())
            output.unlink(missing_ok=True)
            print(f"Pronto: {item['title']}", flush=True)
        except Exception as exc:  # keep the queue commit-able after one bad URL
            item["status"] = "failed"
            item["last_error"] = str(exc)[:1200]
            print(f"Falhou {item.get('title')}: {item['last_error']}", file=sys.stderr, flush=True)


def publish_due(items: list[dict[str, Any]]) -> None:
    token = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
    if not token:
        print("INSTAGRAM_ACCESS_TOKEN ainda não está configurado; publicação ignorada.", flush=True)
        return
    current = now_local()
    for item in items:
        if item.get("status") != "ready":
            continue
        scheduled = parse_dt(item.get("scheduled_at"))
        if not scheduled or scheduled > current:
            continue
        if not item.get("video_url"):
            item["status"] = "failed"
            item["last_error"] = "Item pronto sem video_url"
            continue
        item["status"] = "publishing"
        print(f"A publicar {item.get('title', item_id(item))}", flush=True)
        try:
            result = publish_reel(item["video_url"], CAPTION, token)
            item["status"] = "published"
            item["published_at"] = iso(now_local())
            item["instagram_media_id"] = result.get("id")
            item["instagram_permalink"] = result.get("permalink")
            item["caption"] = CAPTION
            item.pop("last_error", None)
            print(f"Publicado: {result.get('permalink', result.get('id'))}", flush=True)
        except Exception as exc:
            item["status"] = "failed"
            item["last_error"] = str(exc)[:1200]
            print(f"Publicação falhou: {item['last_error']}", file=sys.stderr, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("auto", "prepare", "publish"), default="auto")
    args = parser.parse_args()
    items = load_queue()
    if args.mode in {"auto", "prepare"}:
        prepare_pending(items)
    if args.mode in {"auto", "publish"}:
        publish_due(items)
    save_queue(items)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

