from pathlib import Path
from types import SimpleNamespace

import pytest

from listen_dragon.infrastructure.asr import FasterWhisperRecognizer, TranscriptionError


class FakeWhisperModel:
    def transcribe(self, audio: str, **options):
        assert audio.endswith("audio.wav")
        assert options == {
            "beam_size": 5,
            "vad_filter": True,
            "condition_on_previous_text": False,
        }
        segments = [
            SimpleNamespace(start=0.0, end=1.25, text=" 第一段 "),
            SimpleNamespace(start=1.25, end=2.5, text="第二段"),
        ]
        return segments, SimpleNamespace(language="zh")


def test_faster_whisper_adapter_preserves_timestamps_and_language(tmp_path: Path) -> None:
    created_with = {}

    def model_factory(name: str, **options):
        created_with["name"] = name
        created_with.update(options)
        return FakeWhisperModel()

    recognizer = FasterWhisperRecognizer(
        model_name="base",
        device="cpu",
        compute_type="int8",
        model_factory=model_factory,
    )

    segments = recognizer.transcribe(tmp_path / "audio.wav")

    assert created_with == {"name": "base", "device": "cpu", "compute_type": "int8"}
    assert [(item.start_ms, item.end_ms, item.text, item.language) for item in segments] == [
        (0, 1250, "第一段", "zh"),
        (1250, 2500, "第二段", "zh"),
    ]


def test_faster_whisper_adapter_rejects_empty_transcript(tmp_path: Path) -> None:
    class EmptyModel:
        def transcribe(self, _audio: str, **_options):
            return [], SimpleNamespace(language="zh")

    recognizer = FasterWhisperRecognizer(model_factory=lambda *_args, **_kwargs: EmptyModel())

    with pytest.raises(TranscriptionError) as error:
        recognizer.transcribe(tmp_path / "audio.wav")

    assert error.value.error_code == "ASR_EMPTY"
