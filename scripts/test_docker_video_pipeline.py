from __future__ import annotations

import argparse
import json
import mimetypes
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from verify_video_artifacts import ArtifactValidationError, validate_video_artifacts

SUPPORTED_MIME = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
}

LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def upload_video(api_base: str, video_path: Path) -> dict:
    mime = SUPPORTED_MIME.get(video_path.suffix.lower()) or mimetypes.guess_type(video_path)[0]
    if mime not in SUPPORTED_MIME.values():
        raise RuntimeError(f"Unsupported video extension: {video_path.suffix}")
    boundary = f"----ListenDragonTest{uuid.uuid4().hex}"
    prefix = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{video_path.name}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode()
    body = prefix + video_path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(
        f"{api_base.rstrip('/')}/videos",
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with LOCAL_OPENER.open(request, timeout=120) as response:
        if response.status != 202:
            raise RuntimeError(f"Upload returned HTTP {response.status}")
        return json.loads(response.read())


def get_status(api_base: str, video_id: str) -> dict:
    with LOCAL_OPENER.open(f"{api_base.rstrip('/')}/videos/{video_id}", timeout=30) as response:
        return json.loads(response.read())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Black-box Docker test: upload a real video, wait for READY, validate artifacts"
    )
    parser.add_argument("video", type=Path)
    parser.add_argument("--api-base", default="http://localhost:8000/api/v1")
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    if not args.video.is_file():
        print(json.dumps({"status": "FAILED", "error": f"Video not found: {args.video}"}))
        return 2

    try:
        accepted = upload_video(args.api_base, args.video.resolve())
        video_id = accepted["video_id"]
        print(json.dumps({"event": "uploaded", **accepted}, ensure_ascii=False))
        deadline = time.monotonic() + args.timeout
        last_state = None
        while time.monotonic() < deadline:
            status = get_status(args.api_base, video_id)
            if status["state"] != last_state:
                print(json.dumps({"event": "state_changed", **status}, ensure_ascii=False))
                last_state = status["state"]
            if status["state"] == "FAILED":
                raise RuntimeError(f"Pipeline failed: {status.get('error_code')}")
            if status["state"] == "READY":
                if status.get("progress") != 100:
                    raise RuntimeError(f"READY job has unexpected progress: {status.get('progress')}")
                artifacts = validate_video_artifacts(video_id, args.data_root.resolve())
                print(json.dumps({"status": "PASSED", **artifacts}, ensure_ascii=False, indent=2))
                return 0
            time.sleep(args.poll_seconds)
        raise RuntimeError(f"Timed out after {args.timeout}s; last state={last_state}")
    except (urllib.error.URLError, RuntimeError, ArtifactValidationError, KeyError) as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
