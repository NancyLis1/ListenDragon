"""Record real API answers for manual quality review; no automatic accuracy claims.

Requires an existing READY video and consent for its configured model provider.
Does not read .env, credentials, local media, or upload files. Calls may incur cost.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import UUID

CASES = {
    "camera": [
        "这个视频的主要内容是什么？",
        "他具体是怎么打开它的？请按动作先后说明。",
        "画面里能确定使用了什么工具吗？",
        "打开后接着做了什么？",
        "哪一段能看到打开的动作？",
        "拍摄者的姓名和具体拍摄地址是什么？",
    ],
    "sintel": [
        "这个视频的主要内容是什么？",
        "其中有哪些场景变化？请按出现顺序说明。",
        "画面中出现了什么非人类生物？",
        "对话中的人说自己在寻找什么？",
        "哪一段能看到战斗动作？",
        "这段视频的制作预算是多少？",
    ],
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video-id", type=UUID, required=True)
    parser.add_argument("--case-set", choices=CASES, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-summary", action="store_true")
    args = parser.parse_args()

    def request(path: str, body: dict | None = None) -> tuple[int, dict]:
        data = json.dumps(body).encode() if body is not None else None
        req = Request(args.base_url.rstrip("/") + path, data=data,
                      headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=420) as response:
                return response.status, json.load(response)
        except HTTPError as exc:
            return exc.code, json.load(exc)

    status, video = request(f"/videos/{args.video_id}")
    if status != 200 or video.get("state") != "READY":
        raise SystemExit("Video must already be READY")
    status, conversation = request("/conversations", {"video_id": str(args.video_id)})
    if status != 201:
        raise SystemExit(f"Conversation creation failed: HTTP {status}")
    output = {"video_id": str(args.video_id), "case_set": args.case_set,
              "conversation_id": conversation["conversation_id"], "results": []}
    tasks = [(f"/conversations/{conversation['conversation_id']}/messages", {"question": q})
             for q in CASES[args.case_set]]
    if args.include_summary:
        tasks.append((f"/videos/{args.video_id}/summary", {}))
    for path, body in tasks:
        start = time.monotonic()
        status, result = request(path, body)
        output["results"].append({"request": body, "http_status": status,
                                  "seconds": round(time.monotonic() - start, 2),
                                  "response": result, "manual_verdict": None})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Recorded {len(output['results'])}/{len(tasks)} HTTP {status}", flush=True)


if __name__ == "__main__":
    main()
