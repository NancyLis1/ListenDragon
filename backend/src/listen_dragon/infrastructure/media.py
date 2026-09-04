from __future__ import annotations

import json
import subprocess
from pathlib import Path


class MediaProcessingError(RuntimeError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class FfmpegMediaExtractor:
    def __init__(
        self,
        *,
        ffmpeg_binary: str = "ffmpeg",
        ffprobe_binary: str = "ffprobe",
        max_video_minutes: int = 60,
        timeout_seconds: int = 30 * 60,
    ) -> None:
        self.ffmpeg_binary = ffmpeg_binary
        self.ffprobe_binary = ffprobe_binary
        self.max_video_seconds = max_video_minutes * 60
        self.timeout_seconds = timeout_seconds

    def extract_audio(self, video: Path, output: Path) -> Path:
        duration_seconds = self._probe_duration(video)
        if duration_seconds <= 0:
            raise MediaProcessingError("INVALID_MEDIA", "Video duration must be positive")
        if duration_seconds > self.max_video_seconds:
            raise MediaProcessingError(
                "VIDEO_TOO_LONG",
                f"Video exceeds the {self.max_video_seconds // 60} minute limit",
            )

        output.parent.mkdir(parents=True, exist_ok=True)
        temporary_output = output.with_suffix(".wav.extracting")
        temporary_output.unlink(missing_ok=True)
        command = [
            self.ffmpeg_binary,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            "-f",
            "wav",
            str(temporary_output),
        ]
        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
            if not temporary_output.is_file() or temporary_output.stat().st_size == 0:
                raise MediaProcessingError("AUDIO_EXTRACTION_EMPTY", "FFmpeg produced no audio")
            temporary_output.replace(output)
        except FileNotFoundError as exc:
            raise MediaProcessingError("FFMPEG_UNAVAILABLE", str(exc)) from exc
        except subprocess.TimeoutExpired as exc:
            raise MediaProcessingError("FFMPEG_TIMEOUT", "Audio extraction timed out") from exc
        except subprocess.CalledProcessError as exc:
            message = (exc.stderr or "FFmpeg rejected the uploaded media").strip()
            raise MediaProcessingError("FFMPEG_FAILED", message[-1000:]) from exc
        finally:
            temporary_output.unlink(missing_ok=True)
        return output

    def _probe_duration(self, video: Path) -> float:
        command = [
            self.ffprobe_binary,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(video),
        ]
        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            payload = json.loads(result.stdout)
            return float(payload["format"]["duration"])
        except FileNotFoundError as exc:
            raise MediaProcessingError("FFPROBE_UNAVAILABLE", str(exc)) from exc
        except subprocess.TimeoutExpired as exc:
            raise MediaProcessingError("FFPROBE_TIMEOUT", "Media validation timed out") from exc
        except (
            subprocess.CalledProcessError,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            raise MediaProcessingError("INVALID_MEDIA", "Unable to read video metadata") from exc
