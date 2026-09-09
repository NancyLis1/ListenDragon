"""Audit repository secrets and basic live API security controls.

The audit is non-destructive. It redacts matching values and exits successfully
by default so it can be used to collect evidence even while requirements are
still being implemented. Pass ``--fail-on-findings`` to turn it into a gate.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

SECRET_PATTERNS = {
    "OpenAI-compatible key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "Hugging Face token": re.compile(r"\bhf_[A-Za-z0-9]{20,}\b"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}
TEXT_SUFFIXES = {
    ".env",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}


def request(
    url: str, method: str = "GET", headers: dict[str, str] | None = None
) -> tuple[int, dict[str, str]]:
    req = urllib.request.Request(url, method=method, headers=headers or {})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=20) as response:
            return response.status, {
                key.lower(): value for key, value in response.headers.items()
            }
    except urllib.error.HTTPError as exc:
        return exc.code, {key.lower(): value for key, value in exc.headers.items()}


def tracked_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True
    )
    return [root / item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def scan_secrets(root: Path) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for path in tracked_files(root):
        if path.suffix.lower() not in TEXT_SUFFIXES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for name, pattern in SECRET_PATTERNS.items():
            lines = sorted(
                {
                    text.count("\n", 0, match.start()) + 1
                    for match in pattern.finditer(text)
                }
            )
            if lines:
                findings.append(
                    {"file": str(path.relative_to(root)), "kind": name, "lines": lines}
                )
    return findings


def live_checks(api_base: str) -> list[dict[str, object]]:
    base = api_base.rstrip("/")
    checks: list[dict[str, object]] = []
    status, _ = request(f"{base}/videos")
    checks.append(
        {
            "name": "authentication required for video list",
            "status": status,
            "passed": status in {401, 403},
            "expected": "401 or 403",
        }
    )
    status, _ = request(
        f"{base}/videos/00000000-0000-0000-0000-000000000000", method="DELETE"
    )
    checks.append(
        {
            "name": "video deletion endpoint exists",
            "status": status,
        "passed": status < 500 and status != 405,
            "expected": "not 405",
        }
    )
    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
    }
    status, response_headers = request(
        f"{base}/videos", method="OPTIONS", headers=headers
    )
    checks.append(
        {
            "name": "configured frontend CORS origin allowed",
            "status": status,
            "passed": response_headers.get("access-control-allow-origin")
            == "http://localhost:5173",
            "expected": "allow localhost:5173",
        }
    )
    headers["Origin"] = "https://evil.invalid"
    status, response_headers = request(
        f"{base}/videos", method="OPTIONS", headers=headers
    )
    checks.append(
        {
            "name": "unconfigured CORS origin rejected",
            "status": status,
            "passed": "access-control-allow-origin" not in response_headers,
            "expected": "no allow-origin header",
        }
    )
    status, _ = request(f"{base}/videos/..%2F..%2Fetc%2Fpasswd/content")
    checks.append(
        {
            "name": "path traversal-shaped identifier rejected",
            "status": status,
            "passed": status in {404, 422},
            "expected": "404 or 422",
        }
    )
    return checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--api-base", default="http://localhost:8000/api/v1")
    parser.add_argument("--output", type=Path, default=Path("tmp/security-audit.json"))
    parser.add_argument("--skip-live", action="store_true")
    parser.add_argument("--fail-on-findings", action="store_true")
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    secrets = scan_secrets(repo_root)
    checks = [] if args.skip_live else live_checks(args.api_base)
    report = {
        "suite": "ListenDragon security controls audit",
        "created_at": datetime.now(UTC).isoformat(),
        "secret_scan_scope": "Git-tracked text files; values are never emitted",
        "secret_findings": secrets,
        "live_checks": checks,
        "passed": not secrets and all(item["passed"] for item in checks),
    }
    output = args.output if args.output.is_absolute() else repo_root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if args.fail_on_findings and not report["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
