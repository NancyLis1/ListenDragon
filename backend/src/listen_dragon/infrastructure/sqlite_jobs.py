from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from listen_dragon.domain.models import JobState, VideoJobView
from listen_dragon.services.contracts import DocumentChunk, TranscriptSegment


@dataclass(frozen=True)
class StoredVideo:
    video_id: UUID
    original_name: str
    mime: str
    size_bytes: int
    sha256: str
    source_path: Path
    state: JobState
    progress: int


def sqlite_path_from_url(database_url: str) -> Path:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("ListenDragon MVP only supports sqlite:/// database URLs")
    raw_path = database_url.removeprefix(prefix)
    if not raw_path:
        raise ValueError("SQLite database path cannot be empty")
    return Path(raw_path)


class SqliteJobRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS video (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT,
                    original_name TEXT NOT NULL,
                    mime TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
                    duration_ms INTEGER,
                    sha256 TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    deleted_at TEXT
                );

                CREATE INDEX IF NOT EXISTS ix_video_sha256 ON video(sha256);

                CREATE TABLE IF NOT EXISTS processing_job (
                    id TEXT PRIMARY KEY,
                    video_id TEXT NOT NULL UNIQUE REFERENCES video(id),
                    stage TEXT NOT NULL,
                    state TEXT NOT NULL,
                    progress INTEGER NOT NULL CHECK (progress BETWEEN 0 AND 100),
                    attempt INTEGER NOT NULL DEFAULT 0,
                    lease_owner TEXT,
                    lease_until TEXT,
                    error_code TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS ix_processing_job_state
                    ON processing_job(state, updated_at);

                CREATE TABLE IF NOT EXISTS transcript_segment (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id TEXT NOT NULL REFERENCES video(id),
                    seq INTEGER NOT NULL,
                    start_ms INTEGER NOT NULL,
                    end_ms INTEGER NOT NULL,
                    language TEXT NOT NULL,
                    text TEXT NOT NULL,
                    translated_text TEXT,
                    UNIQUE(video_id, seq),
                    CHECK(start_ms >= 0 AND end_ms > start_ms)
                );

                CREATE TABLE IF NOT EXISTS document_chunk (
                    id TEXT PRIMARY KEY,
                    video_id TEXT NOT NULL REFERENCES video(id),
                    start_ms INTEGER NOT NULL,
                    end_ms INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    token_count INTEGER NOT NULL,
                    embedding_version TEXT NOT NULL DEFAULT '',
                    index_version TEXT NOT NULL DEFAULT '',
                    CHECK(start_ms >= 0 AND end_ms > start_ms)
                );

                CREATE INDEX IF NOT EXISTS ix_transcript_segment_video
                    ON transcript_segment(video_id, seq);
                CREATE INDEX IF NOT EXISTS ix_document_chunk_video
                    ON document_chunk(video_id, start_ms);
                """
            )

    def create_video_job(
        self,
        *,
        video_id: UUID,
        original_name: str,
        mime: str,
        size_bytes: int,
        sha256: str,
        source_path: Path,
    ) -> VideoJobView:
        now = datetime.now(UTC).isoformat()
        job_id = uuid4()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO video (
                    id, original_name, mime, size_bytes, sha256, source_path, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(video_id),
                    original_name,
                    mime,
                    size_bytes,
                    sha256,
                    str(source_path),
                    JobState.queued.value,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO processing_job (
                    id, video_id, stage, state, progress, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(job_id),
                    str(video_id),
                    JobState.queued.value,
                    JobState.queued.value,
                    0,
                    now,
                    now,
                ),
            )
        return VideoJobView(video_id=video_id, state=JobState.queued, progress=0)

    def get_video_job(self, video_id: UUID) -> VideoJobView | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT v.id, j.state, j.progress, j.error_code
                FROM video AS v
                JOIN processing_job AS j ON j.video_id = v.id
                WHERE v.id = ? AND v.deleted_at IS NULL
                """,
                (str(video_id),),
            ).fetchone()
        if row is None:
            return None
        return VideoJobView(
            video_id=UUID(row["id"]),
            state=JobState(row["state"]),
            progress=row["progress"],
            error_code=row["error_code"],
        )

    def claim_audio_extraction(
        self,
        *,
        worker_id: str,
        lease_seconds: int,
    ) -> StoredVideo | None:
        now = datetime.now(UTC)
        now_text = now.isoformat()
        lease_until = (now + timedelta(seconds=lease_seconds)).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT v.id
                FROM video AS v
                JOIN processing_job AS j ON j.video_id = v.id
                WHERE v.deleted_at IS NULL
                  AND (
                    j.state = ?
                    OR (j.state = ? AND j.lease_until < ?)
                  )
                ORDER BY j.created_at
                LIMIT 1
                """,
                (JobState.queued.value, JobState.extracting.value, now_text),
            ).fetchone()
            if row is None:
                return None
            video_id = UUID(row["id"])
            connection.execute(
                """
                UPDATE processing_job
                SET stage = ?, state = ?, progress = ?, attempt = attempt + 1,
                    lease_owner = ?, lease_until = ?, error_code = NULL, updated_at = ?
                WHERE video_id = ?
                """,
                (
                    JobState.extracting.value,
                    JobState.extracting.value,
                    10,
                    worker_id,
                    lease_until,
                    now_text,
                    str(video_id),
                ),
            )
            connection.execute(
                "UPDATE video SET status = ? WHERE id = ?",
                (JobState.extracting.value, str(video_id)),
            )
        return self.get_stored_video(video_id)

    def claim_stage(
        self,
        state: JobState,
        *,
        worker_id: str,
        lease_seconds: int,
    ) -> StoredVideo | None:
        if state not in {JobState.transcribing, JobState.chunking, JobState.indexing}:
            raise ValueError(f"Unsupported claimable stage: {state}")
        now = datetime.now(UTC)
        now_text = now.isoformat()
        lease_until = (now + timedelta(seconds=lease_seconds)).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT v.id
                FROM video AS v
                JOIN processing_job AS j ON j.video_id = v.id
                WHERE v.deleted_at IS NULL
                  AND j.state = ?
                  AND (j.lease_until IS NULL OR j.lease_until < ?)
                ORDER BY j.updated_at
                LIMIT 1
                """,
                (state.value, now_text),
            ).fetchone()
            if row is None:
                return None
            video_id = UUID(row["id"])
            connection.execute(
                """
                UPDATE processing_job
                SET lease_owner = ?, lease_until = ?, attempt = attempt + 1, updated_at = ?
                WHERE video_id = ?
                """,
                (worker_id, lease_until, now_text, str(video_id)),
            )
        return self.get_stored_video(video_id)

    def update_job(
        self,
        video_id: UUID,
        *,
        state: JobState,
        progress: int,
        error_code: str | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE processing_job
                SET stage = ?, state = ?, progress = ?, error_code = ?,
                    lease_owner = NULL, lease_until = NULL, updated_at = ?
                WHERE video_id = ?
                """,
                (state.value, state.value, progress, error_code, now, str(video_id)),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown video job: {video_id}")
            connection.execute(
                "UPDATE video SET status = ? WHERE id = ?",
                (state.value, str(video_id)),
            )

    def replace_transcript_segments(
        self,
        video_id: UUID,
        segments: list[TranscriptSegment],
    ) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM transcript_segment WHERE video_id = ?",
                (str(video_id),),
            )
            connection.executemany(
                """
                INSERT INTO transcript_segment (
                    video_id, seq, start_ms, end_ms, language, text
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        str(video_id),
                        seq,
                        segment.start_ms,
                        segment.end_ms,
                        segment.language,
                        segment.text,
                    )
                    for seq, segment in enumerate(segments)
                ],
            )

    def list_transcript_segments(self, video_id: UUID) -> list[TranscriptSegment]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT start_ms, end_ms, text, language
                FROM transcript_segment
                WHERE video_id = ?
                ORDER BY seq
                """,
                (str(video_id),),
            ).fetchall()
        return [
            TranscriptSegment(
                start_ms=row["start_ms"],
                end_ms=row["end_ms"],
                text=row["text"],
                language=row["language"],
            )
            for row in rows
        ]

    def replace_chunks(self, video_id: UUID, chunks: list[DocumentChunk]) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM document_chunk WHERE video_id = ?",
                (str(video_id),),
            )
            connection.executemany(
                """
                INSERT INTO document_chunk (
                    id, video_id, start_ms, end_ms, text, token_count
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chunk.chunk_id,
                        str(video_id),
                        chunk.start_ms,
                        chunk.end_ms,
                        chunk.text,
                        chunk.token_count,
                    )
                    for chunk in chunks
                ],
            )

    def list_chunks(self, video_id: UUID) -> list[DocumentChunk]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, start_ms, end_ms, text, token_count
                FROM document_chunk
                WHERE video_id = ?
                ORDER BY start_ms, id
                """,
                (str(video_id),),
            ).fetchall()
        return [
            DocumentChunk(
                chunk_id=row["id"],
                start_ms=row["start_ms"],
                end_ms=row["end_ms"],
                text=row["text"],
                token_count=row["token_count"],
            )
            for row in rows
        ]

    def set_chunk_index_version(self, video_id: UUID, index_version: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE document_chunk
                SET index_version = ?
                WHERE video_id = ?
                """,
                (index_version, str(video_id)),
            )

    def get_stored_video(self, video_id: UUID) -> StoredVideo | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT v.id, v.original_name, v.mime, v.size_bytes, v.sha256, v.source_path,
                       j.state, j.progress
                FROM video AS v
                JOIN processing_job AS j ON j.video_id = v.id
                WHERE v.id = ? AND v.deleted_at IS NULL
                """,
                (str(video_id),),
            ).fetchone()
        if row is None:
            return None
        return StoredVideo(
            video_id=UUID(row["id"]),
            original_name=row["original_name"],
            mime=row["mime"],
            size_bytes=row["size_bytes"],
            sha256=row["sha256"],
            source_path=Path(row["source_path"]),
            state=JobState(row["state"]),
            progress=row["progress"],
        )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=10)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA busy_timeout = 5000")
            with connection:
                yield connection
        finally:
            connection.close()
