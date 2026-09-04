from listen_dragon.services.chunking import SemanticChunker
from listen_dragon.services.contracts import TranscriptSegment


def test_chunker_builds_timestamped_overlapping_chunks() -> None:
    chunker = SemanticChunker(
        min_chars=10,
        target_chars=16,
        max_chars=24,
        overlap_chars=5,
    )
    segments = [
        TranscriptSegment(index * 1000, (index + 1) * 1000, f"第{index}段课程内容", "zh")
        for index in range(6)
    ]

    chunks = chunker.split("video-1", segments)

    assert len(chunks) >= 2
    assert all(0 < len(chunk.text) <= 24 for chunk in chunks)
    assert all(chunk.start_ms < chunk.end_ms for chunk in chunks)
    assert chunks[1].start_ms < chunks[0].end_ms
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)


def test_chunker_splits_oversized_segment_and_interpolates_timestamps() -> None:
    chunker = SemanticChunker(
        min_chars=10,
        target_chars=15,
        max_chars=20,
        overlap_chars=5,
    )

    chunks = chunker.split(
        "video-1",
        [TranscriptSegment(1000, 5000, "龙" * 45, "zh")],
    )

    assert len(chunks) == 3
    assert chunks[0].start_ms == 1000
    assert chunks[-1].end_ms == 5000
    assert all(len(chunk.text) <= 20 for chunk in chunks)


def test_chunker_never_exceeds_max_when_two_atoms_barely_do_not_fit() -> None:
    chunker = SemanticChunker(
        min_chars=300,
        target_chars=400,
        max_chars=500,
        overlap_chars=50,
    )
    segments = [
        TranscriptSegment(0, 1000, "甲" * 250, "zh"),
        TranscriptSegment(1000, 2000, "乙" * 250, "zh"),
    ]

    chunks = chunker.split("video-1", segments)

    assert len(chunks) == 2
    assert all(len(chunk.text) <= 500 for chunk in chunks)
