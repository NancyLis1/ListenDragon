import hashlib
import json
import wave
from pathlib import Path

import httpx
import pytest
from scripts.verify_video_artifacts import validate_video_artifacts

from listen_dragon.api.videos import get_job_repository, get_media_extractor
from listen_dragon.core.config import Settings, get_settings
from listen_dragon.infrastructure.indexing import HybridIndexBuilder
from listen_dragon.infrastructure.sqlite_jobs import SqliteJobRepository
from listen_dragon.main import app
from listen_dragon.services.chunking import SemanticChunker
from listen_dragon.services.contracts import ExtractedMedia, TranscriptSegment
from listen_dragon.worker import process_next_job


class WavExtractor:
    def probe_duration(self, video: Path) -> float:
        assert video.read_bytes() == b"controlled-video"
        return 2.0

    def extract_audio(self, video: Path, output: Path) -> ExtractedMedia:
        assert video.read_bytes() == b"controlled-video"
        output.parent.mkdir(parents=True)
        with wave.open(str(output), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(b"\x00\x00" * 160)
        return ExtractedMedia(output, 2_000)


class ChineseRecognizer:
    def transcribe(self, audio: Path) -> list[TranscriptSegment]:
        assert audio.is_file()
        return [
            TranscriptSegment(0, 1000, "第一段中文课程内容。", "zh"),
            TranscriptSegment(1000, 2000, "第二段用于验证完整流水线。", "zh"),
        ]


class DummyEmbeddingModel:
    def encode(self, texts, **options):
        assert options["normalize_embeddings"] is True
        return [[1.0, float(index)] for index, _text in enumerate(texts)]


class DummyFaissIndex:
    def __init__(self, dimension: int) -> None:
        self.dimension = dimension
        self.embeddings = []

    def add(self, embeddings) -> None:
        self.embeddings.extend(embeddings)


class DummyBm25:
    def __init__(self, tokenized) -> None:
        self.tokenized = tokenized


def write_index(index: DummyFaissIndex, path: str) -> None:
    Path(path).write_bytes(json.dumps(index.embeddings).encode())


@pytest.mark.asyncio
async def test_uploaded_video_runs_through_controlled_pipeline_to_ready(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    settings = Settings(
        data_root=str(data_root),
        database_url=f"sqlite:///{(data_root / 'listendragon.db').as_posix()}",
    )
    repository = SqliteJobRepository(data_root / "listendragon.db")
    repository.initialize()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_job_repository] = lambda: repository
    extractor = WavExtractor()
    app.dependency_overrides[get_media_extractor] = lambda: extractor
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            upload = await client.post(
                "/api/v1/videos",
                files={"file": ("中文课程.mp4", b"controlled-video", "video/mp4")},
            )
            assert upload.status_code == 202
            video_id = upload.json()["video_id"]

            builder = HybridIndexBuilder(
                embedding_model="controlled-model",
                model_factory=lambda _name: DummyEmbeddingModel(),
                array_factory=lambda values: values,
                index_factory=DummyFaissIndex,
                index_writer=write_index,
                bm25_factory=DummyBm25,
            )
            dependencies = {
                "repository": repository,
                "extractor": extractor,
                "recognizer": ChineseRecognizer(),
                "chunker": SemanticChunker(
                    min_chars=8, target_chars=16, max_chars=40, overlap_chars=4
                ),
                "index_builder": builder,
                "data_root": data_root,
                "worker_id": "integration-worker",
                "lease_seconds": 60,
            }
            for _ in range(4):
                assert process_next_job(**dependencies)

            status = await client.get(f"/api/v1/videos/{video_id}")
            assert status.status_code == 200
            assert status.json()["state"] == "READY"
            assert status.json()["progress"] == 100

        result = validate_video_artifacts(video_id, data_root)
        assert result["transcript_segments"] == 2
        assert result["chunks"] >= 1
        stored = repository.get_stored_video(video_id)
        assert stored is not None
        assert stored.sha256 == hashlib.sha256(b"controlled-video").hexdigest()
    finally:
        app.dependency_overrides.clear()
