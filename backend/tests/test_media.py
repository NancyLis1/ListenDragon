import json
import subprocess
from pathlib import Path

import pytest

from listen_dragon.infrastructure.media import FfmpegMediaExtractor, MediaProcessingError


def test_ffmpeg_extractor_probes_and_creates_mono_16khz_wav(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    video = tmp_path / "lesson.mp4"
    video.write_bytes(b"video")
    output = tmp_path / "artifacts" / "audio.wav"
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[0] == "ffprobe-test":
            return subprocess.CompletedProcess(
                command,
                returncode=0,
                stdout=json.dumps({"format": {"duration": "12.5"}}),
                stderr="",
            )
        Path(command[-1]).write_bytes(b"wav")
        return subprocess.CompletedProcess(command, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    extractor = FfmpegMediaExtractor(
        ffmpeg_binary="ffmpeg-test",
        ffprobe_binary="ffprobe-test",
        max_video_minutes=60,
    )

    result = extractor.extract_audio(video, output)

    assert result == output
    assert output.read_bytes() == b"wav"
    assert commands[0][0] == "ffprobe-test"
    assert commands[1][0] == "ffmpeg-test"
    assert commands[1][commands[1].index("-ac") + 1] == "1"
    assert commands[1][commands[1].index("-ar") + 1] == "16000"


def test_ffmpeg_extractor_rejects_overlong_video(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    video = tmp_path / "lesson.mp4"
    video.write_bytes(b"video")

    def fake_run(command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            returncode=0,
            stdout=json.dumps({"format": {"duration": "3600.1"}}),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    extractor = FfmpegMediaExtractor(max_video_minutes=60)

    with pytest.raises(MediaProcessingError, match="60 minute") as error:
        extractor.extract_audio(video, tmp_path / "audio.wav")

    assert error.value.error_code == "VIDEO_TOO_LONG"
