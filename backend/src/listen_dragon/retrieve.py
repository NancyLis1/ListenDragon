"""Read-only T12 smoke/evaluation CLI; run inside the configured backend environment."""

import argparse
import json
import statistics
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from listen_dragon.core.config import Settings
from listen_dragon.services.retrieval import RetrievalError, build_retriever


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video_id")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--query")
    action.add_argument("--evaluate", type=Path, help="JSON list of query/answer window records")
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--mode", choices=["vector", "hybrid", "multi"], default="multi")
    parser.add_argument("--output", type=Path, help="Save JSON evidence (refuses to overwrite)")
    parser.add_argument("--include-cloud", action="store_true",
                        help="Explicit consent to send every evaluation query to configured LLM")
    args = parser.parse_args()
    retriever = build_retriever(Settings())
    try:
        if args.query:
            report = retriever.search_detailed(args.video_id, args.query, args.limit, mode=args.mode)
            # No transcript text by default: CLI output is safe to attach as engineering evidence.
            output = {
                "video_id": report.video_id, "index_version": report.index_version,
                "queries": report.queries, "fallback_reason": report.fallback_reason,
                "elapsed_ms": round(report.elapsed_ms, 2),
                "chunks": [{"chunk_id": c.chunk_id, "start_ms": c.start_ms,
                            "end_ms": c.end_ms, "score": c.score} for c in report.chunks],
            }
        else:
            cases = json.loads(args.evaluate.read_text(encoding="utf-8"))
            chunks = retriever.repository.list_chunks(UUID(args.video_id))
            if not isinstance(cases, list) or not cases:
                raise ValueError("Evaluation requires a nonempty JSON list")
            rows = []
            modes = ("vector", "hybrid", "multi") if args.include_cloud else ("vector", "hybrid")
            # Warm-up is recorded separately, never hidden inside latency statistics.
            warmup = retriever.search_detailed(args.video_id, cases[0]["query"], 3, mode="vector")
            for case in cases:
                start, end = case["answer_start_ms"], case["answer_end_ms"]
                gold = {c.chunk_id for c in chunks if c.start_ms <= start and c.end_ms >= end}
                if not gold:
                    raise ValueError(f"No chunk fully contains labeled window: {case['id']}")
                for mode in modes:
                    report = retriever.search_detailed(args.video_id, case["query"], 3, mode=mode)
                    ids = [c.chunk_id for c in report.chunks]
                    rank = next((i for i, key in enumerate(ids, 1) if key in gold), None)
                    rows.append({
                        "case_id": case["id"], "source": case["source"], "mode": mode,
                        "queries": report.queries, "gold_chunk_ids": sorted(gold),
                        "returned_chunk_ids": ids, "first_relevant_rank": rank,
                        "recall_at_3": len(gold.intersection(ids)) / len(gold),
                        "elapsed_ms": round(report.elapsed_ms, 2),
                        "fallback_reason": report.fallback_reason,
                    })
            metrics = {}
            for mode in modes:
                group = [row for row in rows if row["mode"] == mode]
                times = sorted(row["elapsed_ms"] for row in group)
                metrics[mode] = {
                    "count": len(group),
                    "hit_at_1": statistics.mean(row["first_relevant_rank"] == 1 for row in group),
                    "hit_at_3": statistics.mean(row["first_relevant_rank"] is not None for row in group),
                    "recall_at_3": statistics.mean(row["recall_at_3"] for row in group),
                    "mrr_at_3": statistics.mean(
                        1 / row["first_relevant_rank"] if row["first_relevant_rank"] else 0
                        for row in group
                    ),
                    "latency_median_ms": statistics.median(times),
                    "latency_max_ms": max(times),
                    "fallback_count": sum(row["fallback_reason"] is not None for row in group)
                    if mode == "multi" else None,
                }
            output = {
                "created_at": datetime.now(UTC).isoformat(), "video_id": args.video_id,
                "index_version": warmup.index_version, "chunk_count": len(chunks),
                "warmup_ms": round(warmup.elapsed_ms, 2), "metrics": metrics, "rows": rows,
                "limitations": "Single-video development set; ASR-derived windows, not human "
                "frame-verified. No held-out/generalization or final-answer quality claim.",
            }
        serialized = json.dumps(output, ensure_ascii=False, indent=2)
        if args.output:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(serialized + "\n")
            print(json.dumps({"output": str(args.output), "metrics": output.get("metrics")}))
        else:
            print(serialized)
        return 0
    except RetrievalError as exc:
        print(json.dumps({"error_code": exc.error_code}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
