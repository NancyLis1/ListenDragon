import json
from pathlib import Path

import httpx
import pytest

from listen_dragon.infrastructure.vision import FrameAnalyzer, sample_timestamps
from listen_dragon.services.llm_generation import GenerationError, OpenAITextGenerator


def test_sampling_covers_timeline_with_strict_frame_budget():
    times = sample_timestamps(30_000, 3, 24)
    assert len(times) == 11
    assert times[0] == 0 and times[-1] == 29_750
    assert len(sample_timestamps(3_600_000, 3, 24)) == 24
    assert sample_timestamps(1, 3, 24) == [0]


@pytest.mark.parametrize("bad_timestamps", [False, True])
def test_frame_request_contains_images_and_rejects_fabricated_timestamps(
    tmp_path: Path, monkeypatch, bad_timestamps,
):
    def handler(request):
        body = json.loads(request.content)
        content = body["messages"][1]["content"]
        assert content[0]["type"] == "video"
        assert len(content[0]["video"]) == 4
        assert "test-key" not in json.dumps(content)
        observations = [{"timestamp_ms": 999999 if bad_timestamps else 1000,
                         "end_ms": 29000, "text": "可见一个已打开的西瓜。"}]
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
            "content": json.dumps({"observations": observations}),
        }}]})

    generator = OpenAITextGenerator(base_url="https://example.test/v1", api_key="test-key",
                                    model="qwen-test", transport=httpx.MockTransport(handler))
    analyzer = FrameAnalyzer(generator, max_frames=4, window_seconds=30)
    monkeypatch.setattr(analyzer, "_frame", lambda *_: b"\xff\xd8image")
    if bad_timestamps:
        with pytest.raises(GenerationError, match="VISION_INVALID_RESPONSE"):
            analyzer.analyze(tmp_path / "video.mp4", 30000, tmp_path / "frames")
    else:
        result = analyzer.analyze(tmp_path / "video.mp4", 30000, tmp_path / "frames")
        assert [item.timestamp_ms for item in result] == [1000]


def test_vision_provider_diagnostic_is_not_exposed(tmp_path, monkeypatch):
    generator = OpenAITextGenerator(
        base_url="https://example.test/v1", api_key="test-key", model="qwen-test",
        transport=httpx.MockTransport(lambda _: httpx.Response(400, text="private diagnostic")),
    )
    analyzer = FrameAnalyzer(generator, max_frames=4)
    monkeypatch.setattr(analyzer, "_frame", lambda *_: b"\xff\xd8image")
    with pytest.raises(GenerationError, match="LLM_UNAVAILABLE") as error:
        analyzer.analyze(tmp_path / "video.mp4", 30000, tmp_path / "frames")
    assert "private" not in str(error.value)
