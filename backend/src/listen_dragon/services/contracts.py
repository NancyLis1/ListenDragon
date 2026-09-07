from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class TranscriptSegment:
    start_ms: int
    end_ms: int
    text: str
    language: str


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    start_ms: int
    end_ms: int
    text: str
    score: float


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: str
    start_ms: int
    end_ms: int
    text: str
    token_count: int


class MediaExtractor(Protocol):
    def extract_audio(self, video: Path, output: Path) -> Path: ...


class SpeechRecognizer(Protocol):
    def transcribe(self, audio: Path) -> Sequence[TranscriptSegment]: ...


class TextChunker(Protocol):
    def split(
        self,
        video_id: str,
        segments: Sequence[TranscriptSegment],
    ) -> Sequence[DocumentChunk]: ...


class IndexBuilder(Protocol):
    def build(self, chunks: Sequence[DocumentChunk], output_root: Path) -> Path: ...


class HybridRetriever(Protocol):
    def search(self, video_id: str, query: str, limit: int = 6) -> Sequence[RetrievedChunk]: ...


class AnswerGenerator(Protocol):
    def answer(self, question: str, context: Sequence[RetrievedChunk]) -> str: ...
