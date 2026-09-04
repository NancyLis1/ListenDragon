from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass

from listen_dragon.services.contracts import DocumentChunk, TranscriptSegment

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


@dataclass(frozen=True)
class _TextAtom:
    start_ms: int
    end_ms: int
    text: str


class SemanticChunker:
    def __init__(
        self,
        *,
        min_chars: int = 300,
        target_chars: int = 400,
        max_chars: int = 500,
        overlap_chars: int = 50,
    ) -> None:
        if not 0 <= overlap_chars < min_chars <= target_chars <= max_chars:
            raise ValueError("Chunk sizes must satisfy 0 <= overlap < min <= target <= max")
        self.min_chars = min_chars
        self.target_chars = target_chars
        self.max_chars = max_chars
        self.overlap_chars = overlap_chars

    def split(
        self,
        video_id: str,
        segments: Sequence[TranscriptSegment],
    ) -> list[DocumentChunk]:
        atoms = self._to_atoms(segments)
        chunks: list[DocumentChunk] = []
        start_index = 0

        while start_index < len(atoms):
            end_index = start_index
            char_count = 0
            while end_index < len(atoms):
                separator = 1 if char_count else 0
                next_count = char_count + separator + len(atoms[end_index].text)
                if next_count > self.max_chars and char_count:
                    break
                char_count = next_count
                end_index += 1
                if char_count >= self.target_chars:
                    break

            selected = atoms[start_index:end_index]
            text = " ".join(atom.text for atom in selected).strip()
            if text:
                digest = hashlib.sha256(
                    f"{video_id}:{selected[0].start_ms}:{selected[-1].end_ms}:{text}".encode()
                ).hexdigest()[:24]
                chunks.append(
                    DocumentChunk(
                        chunk_id=digest,
                        start_ms=selected[0].start_ms,
                        end_ms=selected[-1].end_ms,
                        text=text,
                        token_count=len(_TOKEN_PATTERN.findall(text)),
                    )
                )

            if end_index >= len(atoms):
                break
            next_start = end_index
            overlap_count = 0
            while next_start > start_index + 1 and overlap_count < self.overlap_chars:
                next_start -= 1
                overlap_count += len(atoms[next_start].text)
            start_index = next_start

        return chunks

    def _to_atoms(self, segments: Sequence[TranscriptSegment]) -> list[_TextAtom]:
        atoms: list[_TextAtom] = []
        for segment in segments:
            text = segment.text.strip()
            if not text:
                continue
            if len(text) <= self.max_chars:
                atoms.append(_TextAtom(segment.start_ms, segment.end_ms, text))
                continue

            part_count = (len(text) + self.max_chars - 1) // self.max_chars
            duration = max(1, segment.end_ms - segment.start_ms)
            for part_index in range(part_count):
                left = part_index * self.max_chars
                right = min(len(text), left + self.max_chars)
                start_ms = segment.start_ms + duration * left // len(text)
                end_ms = segment.start_ms + duration * right // len(text)
                atoms.append(_TextAtom(start_ms, max(start_ms + 1, end_ms), text[left:right]))
        return atoms
