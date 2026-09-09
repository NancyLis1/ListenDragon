"""Black-box functional test for the deployed ListenDragon T13 workflow.

The script uses only Python's standard library. It can reuse a persisted READY
video, or upload a real video and wait for the worker before exercising the
resource, retrieval, summary, and multi-turn QA APIs.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SUPPORTED_MIME = {
    ".mkv": "video/x-matroska",
    ".mov": "video/quicktime",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
}
TIMESTAMP_PATTERN = re.compile(r"^\[\d{2}(?::\d{2}){1,2}-\d{2}(?::\d{2}){1,2}\]$")
LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class FunctionalTestError(RuntimeError):
    """Raised when a black-box functional assertion fails."""


@dataclass
class TestReport:
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    cases: list[dict[str, Any]] = field(default_factory=list)

    def run(self, name: str, action: Callable[[], dict[str, Any] | None]) -> bool:
        started = time.perf_counter()
        try:
            details = action() or {}
            case = {"name": name, "status": "PASSED", "details": details}
            passed = True
        # Keep the suite running so one endpoint failure does not hide later diagnostics.
        except Exception as exc:  # noqa: BLE001
            case = {
                "name": name,
                "status": "FAILED",
                "error": f"{type(exc).__name__}: {exc}",
            }
            passed = False
        case["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
        self.cases.append(case)
        print(json.dumps(case, ensure_ascii=False))
        return passed

    def as_dict(self, *, video_id: str | None, api_base: str) -> dict[str, Any]:
        failures = [case for case in self.cases if case["status"] == "FAILED"]
        return {
            "suite": "ListenDragon T13 live functional test",
            "started_at": self.started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "api_base": api_base,
            "video_id": video_id,
            "status": "PASSED" if not failures else "FAILED",
            "passed": len(self.cases) - len(failures),
            "failed": len(failures),
            "cases": self.cases,
        }


class ApiClient:
    def __init__(self, api_base: str, timeout: float) -> None:
        self.api_base = api_base.rstrip("/")
        parsed = urllib.parse.urlsplit(self.api_base)
        self.origin = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        absolute: bool = False,
    ) -> tuple[int, dict[str, str], bytes]:
        url = f"{self.origin if absolute else self.api_base}{path}"
        body = None
        request_headers = dict(headers or {})
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, method=method, headers=request_headers)
        try:
            with LOCAL_OPENER.open(request, timeout=self.timeout) as response:
                return response.status, dict(response.headers.items()), response.read()
        except urllib.error.HTTPError as exc:
            response_body = exc.read()
            try:
                message = json.loads(response_body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                message = response_body[:500].decode("utf-8", errors="replace")
            raise FunctionalTestError(f"{method} {path} returned HTTP {exc.code}: {message}") from exc
        except urllib.error.URLError as exc:
            raise FunctionalTestError(f"Cannot reach {url}: {exc.reason}") from exc

    def json(
        self, method: str, path: str, *, payload: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        status, _, body = self.request(method, path, payload=payload)
        try:
            return status, json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise FunctionalTestError(f"{method} {path} did not return valid JSON") from exc

    def upload(self, video_path: Path) -> dict[str, Any]:
        mime = SUPPORTED_MIME.get(video_path.suffix.lower()) or mimetypes.guess_type(video_path)[0]
        if mime not in SUPPORTED_MIME.values():
            raise FunctionalTestError(f"Unsupported video extension: {video_path.suffix}")
        boundary = f"----ListenDragonT13{uuid.uuid4().hex}"
        prefix = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{video_path.name}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode()
        suffix = f"\r\n--{boundary}--\r\n".encode("ascii")
        body = prefix + video_path.read_bytes() + suffix
        request = urllib.request.Request(
            f"{self.api_base}/videos",
            data=body,
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        try:
            with LOCAL_OPENER.open(request, timeout=max(self.timeout, 120)) as response:
                if response.status != 202:
                    raise FunctionalTestError(f"Upload returned HTTP {response.status}")
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise FunctionalTestError(
                f"Upload returned HTTP {exc.code}: {exc.read().decode(errors='replace')}"
            ) from exc


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FunctionalTestError(message)


def validate_video(video: dict[str, Any], expected_id: str | None = None) -> None:
    required = {
        "video_id", "original_name", "mime", "size_bytes", "created_at",
        "state", "progress", "error_code",
    }
    require(required <= set(video), f"Video metadata is missing fields: {sorted(required - set(video))}")
    uuid.UUID(video["video_id"])
    if expected_id is not None:
        require(video["video_id"] == expected_id, "Video endpoint returned the wrong video")
    require(video["size_bytes"] > 0, "Persisted video size must be positive")
    require(0 <= video["progress"] <= 100, "Video progress is outside 0..100")


def validate_evidence(items: list[dict[str, Any]], video_id: str) -> None:
    for item in items:
        require(item.get("video_id") == video_id, "Evidence belongs to another video")
        require(bool(item.get("chunk_id")), "Evidence has no chunk_id")
        require(isinstance(item.get("start_ms"), int) and item["start_ms"] >= 0,
                "Evidence start_ms is invalid")
        require(isinstance(item.get("end_ms"), int) and item["end_ms"] > item["start_ms"],
                "Evidence end_ms is invalid")
        require(bool(str(item.get("text", "")).strip()), "Evidence text is empty")
        require(bool(TIMESTAMP_PATTERN.fullmatch(str(item.get("timestamp", "")))),
                "Evidence timestamp has an invalid format")


def wait_until_ready(
    client: ApiClient, video_id: str, *, timeout_seconds: int, poll_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_state = None
    while time.monotonic() < deadline:
        _, video = client.json("GET", f"/videos/{video_id}")
        state = video.get("state")
        if state != last_state:
            print(json.dumps({"event": "state_changed", "state": state,
                              "progress": video.get("progress")}, ensure_ascii=False))
            last_state = state
        if state == "READY":
            require(video.get("progress") == 100, "READY video does not have progress=100")
            return video
        if state == "FAILED":
            raise FunctionalTestError(f"Worker failed with error_code={video.get('error_code')}")
        time.sleep(poll_seconds)
    raise FunctionalTestError(f"Worker timeout after {timeout_seconds}s; last state={last_state}")


def select_video(client: ApiClient, explicit_id: str | None) -> tuple[str, dict[str, Any]]:
    _, listing = client.json("GET", "/videos")
    items = listing.get("items")
    require(isinstance(items, list), "Video list response has no items array")
    if explicit_id:
        matches = [item for item in items if item.get("video_id") == explicit_id]
        require(bool(matches), f"Video {explicit_id} is not present in the persistent video list")
        selected = matches[0]
    else:
        ready = [item for item in items if item.get("state") == "READY"]
        require(bool(ready), "No READY video found; pass --upload or --video-id")
        selected = ready[0]
    validate_video(selected)
    require(selected["state"] == "READY", f"Selected video is {selected['state']}, not READY")
    return selected["video_id"], listing


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test live T13 upload, persistence, media, search, summary, and multi-turn QA"
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--video-id", help="Reuse a persisted READY video")
    source.add_argument("--upload", type=Path, help="Upload this real video and wait for READY")
    parser.add_argument("--api-base", default="http://localhost:8000/api/v1")
    parser.add_argument("--query", default="这个视频主要讲了什么？")
    parser.add_argument("--follow-up", default="请再用一句话概括刚才提到的重点。")
    parser.add_argument("--timeout", type=float, default=90, help="Per-request timeout in seconds")
    parser.add_argument("--worker-timeout", type=int, default=1800)
    parser.add_argument("--poll-seconds", type=float, default=2)
    parser.add_argument("--skip-generation", action="store_true",
                        help="Skip summary and QA when no LLM key is configured")
    parser.add_argument("--output", type=Path, help="Write the JSON report without overwriting")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = ApiClient(args.api_base, args.timeout)
    report = TestReport()
    video_id: str | None = None
    selected: dict[str, Any] | None = None

    report.run("API readiness", lambda: _test_health(client))

    if args.upload:
        def upload_and_process() -> dict[str, Any]:
            nonlocal video_id, selected
            require(args.upload.is_file(), f"Video file not found: {args.upload}")
            accepted = client.upload(args.upload.resolve())
            require(accepted.get("state") == "QUEUED", "Upload was not accepted as QUEUED")
            video_id = accepted["video_id"]
            uuid.UUID(video_id)
            selected = wait_until_ready(
                client, video_id, timeout_seconds=args.worker_timeout,
                poll_seconds=args.poll_seconds,
            )
            return {"video_id": video_id, "original_name": selected["original_name"]}

        report.run("Real upload and worker polling", upload_and_process)

    if video_id is None:
        def persisted_selection() -> dict[str, Any]:
            nonlocal video_id, selected
            video_id, _ = select_video(client, args.video_id)
            _, selected = client.json("GET", f"/videos/{video_id}")
            return {"video_id": video_id, "original_name": selected["original_name"]}

        report.run("Persistent course recovery", persisted_selection)

    if video_id is not None:
        report.run("Video list and metadata", lambda: _test_video_metadata(client, video_id))
        report.run("Published transcript", lambda: _test_transcript(client, video_id))
        report.run("HTTP Range playback", lambda: _test_range(client, video_id))
        report.run("Cross-video search", lambda: _test_search(client, video_id, args.query))
        if not args.skip_generation:
            report.run("Grounded summary and cache", lambda: _test_summary(client, video_id))
            report.run(
                "Persistent multi-turn grounded QA",
                lambda: _test_conversation(client, video_id, args.query, args.follow_up),
            )
    else:
        report.cases.append({
            "name": "Dependent T13 cases",
            "status": "FAILED",
            "error": "No READY video was available after setup",
            "elapsed_ms": 0,
        })

    final = report.as_dict(video_id=video_id, api_base=args.api_base)
    print(json.dumps(final, ensure_ascii=False, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        try:
            with args.output.open("x", encoding="utf-8", errors="strict") as stream:
                stream.write(json.dumps(final, ensure_ascii=False, indent=2) + "\n")
        except FileExistsError:
            raise FunctionalTestError(f"Refusing to overwrite report: {args.output}")
    return 0 if final["status"] == "PASSED" else 1


def _test_health(client: ApiClient) -> dict[str, Any]:
    # Health endpoints are outside /api/v1, so use an absolute-origin request.
    status, _, raw = client.request("GET", "/health/ready", absolute=True)
    data = json.loads(raw)
    require(status == 200, "Readiness endpoint did not return HTTP 200")
    return data


def _test_video_metadata(client: ApiClient, video_id: str) -> dict[str, Any]:
    _, listing = client.json("GET", "/videos")
    matches = [item for item in listing.get("items", []) if item.get("video_id") == video_id]
    require(len(matches) == 1, "Persistent list must contain the selected video exactly once")
    _, detail = client.json("GET", f"/videos/{video_id}")
    validate_video(detail, video_id)
    require(detail["state"] == "READY" and detail["progress"] == 100,
            "Video metadata is not READY/100")
    require(matches[0] == detail, "List and detail metadata do not match")
    return {"original_name": detail["original_name"], "duration_ms": detail.get("duration_ms")}


def _test_transcript(client: ApiClient, video_id: str) -> dict[str, Any]:
    _, body = client.json("GET", f"/videos/{video_id}/transcript")
    require(body.get("video_id") == video_id, "Transcript returned the wrong video_id")
    segments = body.get("segments")
    require(isinstance(segments, list) and segments, "Transcript has no published segments")
    for expected_seq, segment in enumerate(segments):
        require(segment.get("seq") == expected_seq, "Transcript sequence is not contiguous")
        require(segment.get("start_ms", -1) >= 0, "Transcript start_ms is invalid")
        require(segment.get("end_ms", 0) > segment["start_ms"], "Transcript time range is invalid")
        require(bool(str(segment.get("text", "")).strip()), "Transcript contains empty text")
        require(bool(segment.get("language")), "Transcript segment has no language")
    return {"segments": len(segments), "last_end_ms": segments[-1]["end_ms"]}


def _test_range(client: ApiClient, video_id: str) -> dict[str, Any]:
    status, headers, body = client.request(
        "GET", f"/videos/{video_id}/content", headers={"Range": "bytes=0-0"}
    )
    lower_headers = {key.lower(): value for key, value in headers.items()}
    require(status == 206, f"Range request returned HTTP {status}, expected 206")
    require(len(body) == 1, f"Range request returned {len(body)} bytes, expected 1")
    require(lower_headers.get("content-range", "").startswith("bytes 0-0/"),
            "Range response has no valid Content-Range")
    return {"content_range": lower_headers["content-range"]}


def _test_search(client: ApiClient, video_id: str, query: str) -> dict[str, Any]:
    _, body = client.json("POST", "/search", payload={
        "query": query, "video_ids": [video_id], "limit": 20,
    })
    results = body.get("results")
    require(isinstance(results, list) and results, "Search returned no results")
    previous_score = float("inf")
    for item in results:
        require(item.get("video_id") == video_id, "Search leaked a result from another video")
        require(item.get("end_ms", 0) > item.get("start_ms", -1) >= 0,
                "Search result has an invalid time range")
        require(bool(str(item.get("text", "")).strip()), "Search result text is empty")
        require(item.get("score", 0) <= previous_score, "Search results are not score-sorted")
        previous_score = item["score"]
    return {"query": query, "results": len(results), "top_score": results[0]["score"]}


def _test_summary(client: ApiClient, video_id: str) -> dict[str, Any]:
    payload = {"language": "auto", "length": "medium", "format": "outline"}
    _, first = client.json("POST", f"/videos/{video_id}/summary", payload=payload)
    _, second = client.json("POST", f"/videos/{video_id}/summary", payload=payload)
    for item in (first, second):
        require(item.get("video_id") == video_id, "Summary returned the wrong video_id")
        require(bool(str(item.get("summary", "")).strip()), "Summary text is empty")
        evidence = item.get("evidence")
        require(isinstance(evidence, list) and evidence, "Summary has no evidence")
        validate_evidence(evidence, video_id)
        for cited in evidence:
            require(cited["timestamp"] in item["summary"],
                    "Summary evidence timestamp is not present in summary text")
    require(second.get("cached") is True, "Second identical summary request did not hit cache")
    return {"first_cached": first.get("cached"), "second_cached": second["cached"],
            "evidence": len(second["evidence"])}


def _test_conversation(
    client: ApiClient, video_id: str, question: str, follow_up: str,
) -> dict[str, Any]:
    status, created = client.json("POST", "/conversations", payload={"video_id": video_id})
    require(status == 201, f"Conversation creation returned HTTP {status}")
    conversation_id = created.get("conversation_id")
    uuid.UUID(conversation_id)
    require(created.get("video_id") == video_id, "Conversation is bound to another video")
    answers = []
    for prompt in (question, follow_up):
        _, answer = client.json(
            "POST", f"/conversations/{conversation_id}/messages", payload={"question": prompt}
        )
        require(answer.get("conversation_id") == conversation_id,
                "Answer returned another conversation_id")
        uuid.UUID(answer["message_id"])
        require(bool(str(answer.get("answer", "")).strip()), "Answer text is empty")
        evidence = answer.get("evidence")
        require(isinstance(evidence, list), "Answer evidence is not an array")
        if answer.get("refused"):
            require(not evidence, "A refused answer must not contain evidence")
        else:
            require(bool(evidence), "A non-refused answer has no evidence")
            validate_evidence(evidence, video_id)
            for cited in evidence:
                require(cited["timestamp"] in answer["answer"],
                        "Answer evidence timestamp is not present in answer text")
        answers.append(answer)
    require(any(not answer["refused"] for answer in answers),
            "Both answerable course questions were refused")
    return {
        "conversation_id": conversation_id,
        "turns": len(answers),
        "refused": [answer["refused"] for answer in answers],
        "evidence_counts": [len(answer["evidence"]) for answer in answers],
    }


if __name__ == "__main__":
    raise SystemExit(main())
