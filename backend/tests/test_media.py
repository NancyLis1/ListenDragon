import json
import subprocess
import sys
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

    assert result.audio_path == output
    assert result.duration_ms == 12_500
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


def test_ffmpeg_extractor_accepts_exact_duration_limit(tmp_path, monkeypatch):
    output = tmp_path / "audio.wav"
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command[0] == "ffprobe":
            return subprocess.CompletedProcess(command, 0, json.dumps({"format": {"duration": "3600"}}))
        output.with_suffix(".wav.extracting").write_bytes(b"audio")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", run)
    result = FfmpegMediaExtractor(max_video_minutes=60).extract_audio(tmp_path / "video.mp4", output)
    assert result.duration_ms == 3_600_000
    assert output.read_bytes() == b"audio"
    assert len(calls) == 2


@pytest.mark.parametrize("phase", ["probe", "extract"])
def test_media_errors_survive_non_locale_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str,
) -> None:
    real_run = subprocess.run

    def run_child(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        if phase == "extract" and command[0] == "ffprobe":
            return subprocess.CompletedProcess(
                command, 0, stdout='{"format":{"duration":"1"}}', stderr="",
            )
        # A real child process emits UTF-8 plus an invalid byte, independent of OS locale.
        return real_run([
            sys.executable, "-c",
            ("import sys; sys.stderr.buffer.write('媒体损坏'.encode('utf-8') + bytes([255]));"
             "sys.exit(1)"),
        ], **kwargs)

    monkeypatch.setattr(subprocess, "run", run_child)
    with pytest.raises(MediaProcessingError) as error:
        FfmpegMediaExtractor().extract_audio(tmp_path / "中文.mp4", tmp_path / "audio.wav")
    assert error.value.error_code == ("INVALID_MEDIA" if phase == "probe" else "FFMPEG_FAILED")
    if phase == "extract":
        assert "媒体损坏" in str(error.value)
