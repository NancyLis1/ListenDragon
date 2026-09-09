"""Evaluate ListenDragon's faster-whisper settings on AISHELL-1.

Run this script through ``scripts/run_aishell_cer_test.ps1`` so it executes in
the existing Worker container and reuses the model already cached there.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import unicodedata
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class SampleResult:
    utterance_id: str
    audio_path: str
    reference: str
    hypothesis: str
    normalized_reference: str
    normalized_hypothesis: str
    edits: int
    reference_chars: int
    cer: float
    elapsed_seconds: float


def normalize_for_cer(text: str) -> str:
    """Apply a documented, conservative normalization before Chinese CER."""
    normalized = unicodedata.normalize("NFKC", text).upper()
    return "".join(
        character
        for character in normalized
        if not unicodedata.category(character).startswith(("P", "S", "Z", "C"))
    )


def edit_distance(reference: str, hypothesis: str) -> int:
    """Return character-level Levenshtein distance using O(len(hypothesis)) memory."""
    if len(reference) < len(hypothesis):
        reference, hypothesis = hypothesis, reference
    previous = list(range(len(hypothesis) + 1))
    for row, reference_char in enumerate(reference, start=1):
        current = [row]
        for column, hypothesis_char in enumerate(hypothesis, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (reference_char != hypothesis_char),
                )
            )
        previous = current
    return previous[-1]


def find_dataset_root(candidate: Path) -> Path:
    candidate = candidate.resolve()
    possibilities = (candidate, candidate / "data_aishell")
    for root in possibilities:
        if (root / "transcript" / "aishell_transcript_v0.8.txt").is_file():
            return root
    raise FileNotFoundError(
        "AISHELL-1 was not extracted correctly: expected "
        "data_aishell/transcript/aishell_transcript_v0.8.txt"
    )


def load_references(dataset_root: Path) -> dict[str, str]:
    transcript = dataset_root / "transcript" / "aishell_transcript_v0.8.txt"
    references: dict[str, str] = {}
    with transcript.open(encoding="utf-8") as stream:
        for line in stream:
            fields = line.strip().split(maxsplit=1)
            if len(fields) == 2:
                references[fields[0]] = fields[1]
    if not references:
        raise ValueError(f"No references were found in {transcript}")
    return references


def discover_audio(dataset_root: Path, split: str) -> list[Path]:
    split_root = dataset_root / "wav" / split
    if not split_root.is_dir():
        raise FileNotFoundError(
            f"AISHELL-1 split is missing: {split_root}. "
            "Extract the nested wav archives before evaluation."
        )
    audio = sorted(split_root.rglob("*.wav"))
    if not audio:
        raise FileNotFoundError(f"No WAV files found below {split_root}")
    return audio


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure character error rate on AISHELL-1")
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--split", choices=("dev", "test"), default="test")
    parser.add_argument("--limit", type=int, default=500, help="0 evaluates the full split")
    parser.add_argument("--seed", type=int, default=20260909)
    parser.add_argument("--model", default=os.getenv("ASR_MODEL", "base"))
    parser.add_argument("--device", default=os.getenv("ASR_DEVICE", "cpu"))
    parser.add_argument("--compute-type", default=os.getenv("ASR_COMPUTE_TYPE", "int8"))
    parser.add_argument("--threshold", type=float, default=0.08)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--fail-on-threshold",
        action="store_true",
        help="Return exit code 1 when CER is not below --threshold",
    )
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be zero or a positive integer")
    if not 0 <= args.threshold <= 1:
        parser.error("--threshold must be between zero and one")
    return args


def main() -> int:
    args = parse_args()
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("faster-whisper is missing; run this script in the Worker container", file=sys.stderr)
        return 2

    dataset_root = find_dataset_root(args.dataset_root)
    references = load_references(dataset_root)
    audio_paths = discover_audio(dataset_root, args.split)
    missing_references = [path.stem for path in audio_paths if path.stem not in references]
    if missing_references:
        raise ValueError(f"Missing references for {len(missing_references)} WAV files")

    if args.limit and args.limit < len(audio_paths):
        audio_paths = random.Random(args.seed).sample(audio_paths, args.limit)
        audio_paths.sort()

    print(
        f"Loading faster-whisper model={args.model} device={args.device} "
        f"compute_type={args.compute_type}",
        flush=True,
    )
    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)
    started = time.perf_counter()
    results: list[SampleResult] = []
    total_edits = 0
    total_reference_chars = 0

    for index, audio_path in enumerate(audio_paths, start=1):
        sample_started = time.perf_counter()
        segments, _ = model.transcribe(
            str(audio_path),
            beam_size=5,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        hypothesis = "".join(segment.text.strip() for segment in segments)
        reference = references[audio_path.stem]
        normalized_reference = normalize_for_cer(reference)
        normalized_hypothesis = normalize_for_cer(hypothesis)
        edits = edit_distance(normalized_reference, normalized_hypothesis)
        reference_chars = len(normalized_reference)
        if not reference_chars:
            raise ValueError(f"Reference became empty after normalization: {audio_path.stem}")
        result = SampleResult(
            utterance_id=audio_path.stem,
            audio_path=str(audio_path.relative_to(dataset_root)),
            reference=reference,
            hypothesis=hypothesis,
            normalized_reference=normalized_reference,
            normalized_hypothesis=normalized_hypothesis,
            edits=edits,
            reference_chars=reference_chars,
            cer=edits / reference_chars,
            elapsed_seconds=round(time.perf_counter() - sample_started, 3),
        )
        results.append(result)
        total_edits += edits
        total_reference_chars += reference_chars
        if args.verbose or index % 25 == 0 or index == len(audio_paths):
            running_cer = total_edits / total_reference_chars
            print(
                f"[{index}/{len(audio_paths)}] {audio_path.stem} "
                f"sample_cer={result.cer:.2%} running_cer={running_cer:.2%}",
                flush=True,
            )

    cer = total_edits / total_reference_chars
    elapsed_seconds = time.perf_counter() - started
    report = {
        "suite": "AISHELL-1 Chinese ASR CER evaluation",
        "created_at": datetime.now(UTC).isoformat(),
        "dataset": "AISHELL-1",
        "split": args.split,
        "sample_count": len(results),
        "sampling_seed": args.seed,
        "model": args.model,
        "device": args.device,
        "compute_type": args.compute_type,
        "normalization": "Unicode NFKC; uppercase; remove punctuation, symbols, separators and controls",
        "total_edits": total_edits,
        "total_reference_chars": total_reference_chars,
        "cer": cer,
        "character_accuracy": 1 - cer,
        "threshold": args.threshold,
        "passed": cer < args.threshold,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "samples": [asdict(result) for result in results],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".writing")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(args.output)
    print(
        json.dumps(
            {
                "sample_count": len(results),
                "cer": cer,
                "character_accuracy": 1 - cer,
                "threshold": args.threshold,
                "passed": cer < args.threshold,
                "elapsed_seconds": round(elapsed_seconds, 3),
                "report": str(args.output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if args.fail_on_threshold and cer >= args.threshold else 0


if __name__ == "__main__":
    raise SystemExit(main())
