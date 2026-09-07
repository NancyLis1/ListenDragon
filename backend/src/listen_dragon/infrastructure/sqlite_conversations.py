from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from listen_dragon.domain.models import EvidenceView


@dataclass(frozen=True)
class StoredConversation:
    conversation_id: UUID
    video_id: UUID
    memory_summary: str
    revision: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class StoredMessage:
    message_id: UUID
    conversation_id: UUID
    role: str
    content: str
    evidence: tuple[EvidenceView, ...]
    created_at: datetime


@dataclass(frozen=True)
class StoredSummary:
    video_id: UUID
    content: str
    evidence: tuple[EvidenceView, ...]
    generated_at: datetime


class ConversationConflictError(RuntimeError):
    pass


class SqliteConversationRepository:
    """Durable conversation, evidence, and summary storage on the shared SQLite DB."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversation (
                    id TEXT PRIMARY KEY,
                    video_id TEXT NOT NULL REFERENCES video(id),
                    memory_summary TEXT NOT NULL DEFAULT '',
                    revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS ix_conversation_video
                    ON conversation(video_id, updated_at);

                CREATE TABLE IF NOT EXISTS message (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversation(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL CHECK (position >= 0),
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    UNIQUE(conversation_id, position)
                );

                CREATE INDEX IF NOT EXISTS ix_message_conversation
                    ON message(conversation_id, position);

                CREATE TABLE IF NOT EXISTS video_summary (
                    id TEXT PRIMARY KEY,
                    video_id TEXT NOT NULL REFERENCES video(id),
                    index_version TEXT NOT NULL,
                    language TEXT NOT NULL,
                    length TEXT NOT NULL,
                    format TEXT NOT NULL,
                    content TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    UNIQUE(video_id, index_version, language, length, format)
                );
                """
            )

    def create_conversation(self, video_id: UUID) -> StoredConversation:
        conversation_id = uuid4()
        now = datetime.now(UTC)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO conversation (id, video_id, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (str(conversation_id), str(video_id), now.isoformat(), now.isoformat()),
            )
        return StoredConversation(conversation_id, video_id, "", 0, now, now)

    def get_conversation(self, conversation_id: UUID) -> StoredConversation | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, video_id, memory_summary, revision, created_at, updated_at
                FROM conversation WHERE id = ?
                """,
                (str(conversation_id),),
            ).fetchone()
        if row is None:
            return None
        return StoredConversation(
            conversation_id=UUID(row["id"]),
            video_id=UUID(row["video_id"]),
            memory_summary=row["memory_summary"],
            revision=row["revision"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def append_exchange(
        self,
        *,
        conversation_id: UUID,
        expected_revision: int,
        question: str,
        answer: str,
        evidence: Sequence[EvidenceView],
        memory_summary: str,
    ) -> StoredMessage:
        user_message_id = uuid4()
        assistant_message_id = uuid4()
        now = datetime.now(UTC)
        evidence_json = json.dumps(
            [item.model_dump(mode="json") for item in evidence],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE conversation
                SET memory_summary = ?, revision = revision + 1, updated_at = ?
                WHERE id = ? AND revision = ?
                """,
                (
                    memory_summary,
                    now.isoformat(),
                    str(conversation_id),
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise ConversationConflictError("Conversation changed during answer generation")
            connection.executemany(
                """
                INSERT INTO message (
                    id, conversation_id, position, role, content, evidence_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        str(user_message_id),
                        str(conversation_id),
                        expected_revision * 2,
                        "user",
                        question,
                        "[]",
                        now.isoformat(),
                    ),
                    (
                        str(assistant_message_id),
                        str(conversation_id),
                        expected_revision * 2 + 1,
                        "assistant",
                        answer,
                        evidence_json,
                        now.isoformat(),
                    ),
                ],
            )
        return StoredMessage(
            assistant_message_id,
            conversation_id,
            "assistant",
            answer,
            tuple(evidence),
            now,
        )

    def list_messages(self, conversation_id: UUID) -> list[StoredMessage]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, conversation_id, role, content, evidence_json, created_at
                FROM message WHERE conversation_id = ? ORDER BY position
                """,
                (str(conversation_id),),
            ).fetchall()
        return [
            StoredMessage(
                message_id=UUID(row["id"]),
                conversation_id=UUID(row["conversation_id"]),
                role=row["role"],
                content=row["content"],
                evidence=tuple(
                    EvidenceView.model_validate(item) for item in json.loads(row["evidence_json"])
                ),
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def get_summary(
        self,
        *,
        video_id: UUID,
        index_version: str,
        language: str,
        length: str,
        format: str,
    ) -> StoredSummary | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT content, evidence_json, generated_at
                FROM video_summary
                WHERE video_id = ? AND index_version = ? AND language = ?
                    AND length = ? AND format = ?
                """,
                (str(video_id), index_version, language, length, format),
            ).fetchone()
        if row is None:
            return None
        return StoredSummary(
            video_id=video_id,
            content=row["content"],
            evidence=tuple(
                EvidenceView.model_validate(item) for item in json.loads(row["evidence_json"])
            ),
            generated_at=datetime.fromisoformat(row["generated_at"]),
        )

    def save_summary(
        self,
        *,
        video_id: UUID,
        index_version: str,
        language: str,
        length: str,
        format: str,
        content: str,
        evidence: Sequence[EvidenceView],
    ) -> StoredSummary:
        generated_at = datetime.now(UTC)
        evidence_json = json.dumps(
            [item.model_dump(mode="json") for item in evidence],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO video_summary (
                    id, video_id, index_version, language, length, format,
                    content, evidence_json, generated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_id, index_version, language, length, format)
                DO UPDATE SET content = excluded.content,
                              evidence_json = excluded.evidence_json,
                              generated_at = excluded.generated_at
                """,
                (
                    str(uuid4()),
                    str(video_id),
                    index_version,
                    language,
                    length,
                    format,
                    content,
                    evidence_json,
                    generated_at.isoformat(),
                ),
            )
        return StoredSummary(video_id, content, tuple(evidence), generated_at)

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
