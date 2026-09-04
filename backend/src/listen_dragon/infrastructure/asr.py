from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from listen_dragon.services.contracts import TranscriptSegment


class TranscriptionError(RuntimeError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class FasterWhisperRecognizer:
    def __init__(
        self,
        *,
        model_name: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        model_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self._model_factory = model_factory
        self._model: Any | None = None

    def transcribe(self, audio: Path) -> list[TranscriptSegment]:
        try:
            model = self._get_model()
            raw_segments, info = model.transcribe(
                str(audio),
                beam_size=5,
                vad_filter=True,
                condition_on_previous_text=False,
            )
            language = getattr(info, "language", "unknown") or "unknown"
            result = []
            for segment in raw_segments:
                text = segment.text.strip()
                if not text:
                    continue
                start_ms = max(0, round(segment.start * 1000))
                end_ms = max(start_ms + 1, round(segment.end * 1000))
                result.append(
                    TranscriptSegment(
                        start_ms=start_ms,
                        end_ms=end_ms,
                        text=text,
                        language=language,
                    )
                )
        except TranscriptionError:
            raise
        except Exception as exc:
            raise TranscriptionError("ASR_FAILED", str(exc)) from exc
        if not result:
            raise TranscriptionError("ASR_EMPTY", "Whisper produced no transcript segments")
        return result

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        factory = self._model_factory
        if factory is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise TranscriptionError(
                    "ASR_UNAVAILABLE",
                    "faster-whisper is not installed; install the backend ai extra",
                ) from exc
            factory = WhisperModel
        self._model = factory(
            self.model_name,
            device=self.device,
            compute_type=self.compute_type,
        )
        return self._model
