"""Collect repeatable API latency samples and AISHELL ASR real-time factor."""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.request
import wave
from datetime import UTC, datetime
from pathlib import Path


def call(
    url: str, *, data: bytes | None = None, headers: dict[str, str] | None = None
) -> tuple[float, object]:
    request = urllib.request.Request(url, data=data, headers=headers or {})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    started = time.perf_counter()
    with opener.open(request, timeout=120) as response:
        body = response.read()
        content_type = response.headers.get("Content-Type", "")
    elapsed_ms = (time.perf_counter() - started) * 1000
    return elapsed_ms, json.loads(body) if "json" in content_type else len(body)


def aishell_metrics(report_path: Path, dataset_root: Path) -> dict[str, float | int]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    duration = 0.0
    for sample in report["samples"]:
        with wave.open(str(dataset_root / sample["audio_path"]), "rb") as stream:
            duration += stream.getnframes() / stream.getframerate()
    elapsed = float(report["elapsed_seconds"])
    return {
        "sample_count": int(report["sample_count"]),
        "audio_duration_seconds": round(duration, 3),
        "inference_elapsed_seconds": round(elapsed, 3),
        "real_time_factor": round(elapsed / duration, 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default="http://localhost:8000/api/v1")
    parser.add_argument("--video-id")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--query", default="这个视频主要讲了什么？")
    parser.add_argument("--aishell-report", type=Path)
    parser.add_argument("--aishell-root", type=Path)
    parser.add_argument(
        "--output", type=Path, default=Path("tmp/system-performance.json")
    )
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")

    base = args.api_base.rstrip("/")
    _, listing = call(f"{base}/videos")
    items = listing["items"]
    ready_ids = [item["video_id"] for item in items if item["state"].upper() == "READY"]
    video_id = args.video_id or (ready_ids[0] if ready_ids else None)
    if not video_id:
        raise RuntimeError("No ready video is available; pass --video-id")
    if video_id not in ready_ids:
        ready_ids.append(video_id)

    samples: dict[str, list[float]] = {
        name: []
        for name in ("video_metadata", "transcript", "range_playback", "hybrid_search")
    }
    for _ in range(args.runs):
        samples["video_metadata"].append(call(f"{base}/videos/{video_id}")[0])
        samples["transcript"].append(call(f"{base}/videos/{video_id}/transcript")[0])
        samples["range_playback"].append(
            call(f"{base}/videos/{video_id}/content", headers={"Range": "bytes=0-0"})[0]
        )
        payload = json.dumps(
            {"video_ids": ready_ids, "query": args.query, "limit": 6},
            ensure_ascii=False,
        ).encode("utf-8")
        samples["hybrid_search"].append(
            call(
                f"{base}/search",
                data=payload,
                headers={"Content-Type": "application/json"},
            )[0]
        )

    summary = {
        name: {
            "runs": [round(value, 2) for value in values],
            "median_ms": round(statistics.median(values), 2),
            "max_ms": round(max(values), 2),
        }
        for name, values in samples.items()
    }
    report: dict[str, object] = {
        "suite": "ListenDragon repeatable system performance sampling",
        "created_at": datetime.now(UTC).isoformat(),
        "runs": args.runs,
        "video_id": video_id,
        "api_latency": summary,
        "note": "The current QA API is synchronous, so first-token latency cannot be measured.",
    }
    if args.aishell_report and args.aishell_root:
        report["asr"] = aishell_metrics(args.aishell_report, args.aishell_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
