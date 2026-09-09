"""Prepare AISHELL-1 from the official archive or test-only Parquet shards."""

from __future__ import annotations

import argparse
import tarfile
from pathlib import Path


def extract_archive(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:*") as package:
        package.extractall(destination, filter="data")


def safe_relative_path(value: str) -> Path:
    candidate = Path(value.replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"Unsafe dataset path: {value}")
    return candidate


def extract_parquet(parquet_dir: Path, destination: Path) -> None:
    try:
        from pyarrow import parquet
    except ImportError as exc:
        raise RuntimeError("Install pyarrow before extracting Parquet shards") from exc

    shards = sorted(parquet_dir.glob("*.parquet"))
    if not shards:
        raise FileNotFoundError(f"No Parquet shards found in {parquet_dir}")
    dataset_root = destination / "data_aishell"
    transcript_path = dataset_root / "transcript" / "aishell_transcript_v0.8.txt"
    references: dict[str, str] = {}
    written = 0
    for shard_index, shard in enumerate(shards, start=1):
        print(f"[{shard_index}/{len(shards)}] Reading {shard.name}", flush=True)
        source = parquet.ParquetFile(shard)
        required = {"name", "WavPath", "text", "audio"}
        if not required.issubset(source.schema_arrow.names):
            raise ValueError(f"Unexpected columns in {shard}: {source.schema_arrow.names}")
        for batch in source.iter_batches(batch_size=64, columns=sorted(required)):
            for row in batch.to_pylist():
                utterance_id = str(row["name"])
                references[utterance_id] = str(row["text"])
                audio = row["audio"]
                audio_bytes = audio.get("bytes") if isinstance(audio, dict) else None
                if not audio_bytes:
                    raise ValueError(f"No embedded audio bytes for {utterance_id}")
                relative = safe_relative_path(str(row["WavPath"]))
                output = dataset_root / "wav" / relative
                output.parent.mkdir(parents=True, exist_ok=True)
                if not output.is_file() or output.stat().st_size != len(audio_bytes):
                    temporary = output.with_suffix(output.suffix + ".writing")
                    temporary.write_bytes(audio_bytes)
                    temporary.replace(output)
                written += 1

    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_text = "".join(
        f"{utterance_id} {references[utterance_id]}\n" for utterance_id in sorted(references)
    )
    temporary_transcript = transcript_path.with_suffix(".txt.writing")
    temporary_transcript.write_text(transcript_text, encoding="utf-8")
    temporary_transcript.replace(transcript_path)
    print(f"Extracted {written} test utterances from {len(shards)} Parquet shards", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--archive", type=Path)
    source.add_argument("--parquet-dir", type=Path)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    destination = args.destination.resolve()
    if args.parquet_dir:
        extract_parquet(args.parquet_dir.resolve(), destination)
    else:
        archive = args.archive.resolve()
        if not archive.is_file():
            raise FileNotFoundError(archive)
        transcript = destination / "data_aishell" / "transcript" / "aishell_transcript_v0.8.txt"
        if not transcript.is_file():
            print(f"Extracting outer archive: {archive}", flush=True)
            extract_archive(archive, destination)

        wav_root = destination / "data_aishell" / "wav"
        nested = sorted(wav_root.rglob("*.tar.gz"))
        if not nested and not any(wav_root.rglob("*.wav")):
            raise FileNotFoundError(f"No nested archives or WAV files found below {wav_root}")
        for index, package in enumerate(nested, start=1):
            print(f"[{index}/{len(nested)}] Extracting {package}", flush=True)
            extract_archive(package, package.parent)

    wav_root = destination / "data_aishell" / "wav"
    test_count = sum(1 for _ in (wav_root / "test").rglob("*.wav"))
    dev_count = sum(1 for _ in (wav_root / "dev").rglob("*.wav"))
    print(f"AISHELL-1 ready: dev_wav={dev_count}, test_wav={test_count}")


if __name__ == "__main__":
    main()
