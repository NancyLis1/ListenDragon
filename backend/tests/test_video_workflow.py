import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest

from listen_dragon.domain.models import JobState, SummaryRequest, VisualAnalysisView
from listen_dragon.infrastructure.sqlite_conversations import SqliteConversationRepository
from listen_dragon.infrastructure.sqlite_jobs import SqliteJobRepository
from listen_dragon.infrastructure.vision import FrameAnalyzer
from listen_dragon.services.contracts import DocumentChunk
from listen_dragon.services.grounded_generation import GroundedGenerationService, ServiceError
from listen_dragon.services.llm_generation import OpenAITextGenerator


class EmptyRetriever:
    def search(self, *args, **kwargs):
        return []


@pytest.fixture
def workflow(tmp_path, monkeypatch):
    jobs = SqliteJobRepository(tmp_path / "app.db")
    jobs.initialize()
    conversations = SqliteConversationRepository(tmp_path / "app.db")
    conversations.initialize()
    video_id = uuid4()
    source = tmp_path / "uploads" / "video.mp4"
    source.parent.mkdir()
    source.write_bytes(b"video")
    jobs.create_video_job(video_id=video_id, original_name="video.mp4", mime="video/mp4",
                          size_bytes=5, sha256="0" * 64, source_path=source)
    jobs.set_video_duration(video_id, 30000)
    jobs.replace_chunks(video_id, [DocumentChunk(f"visual:{video_id}:1", 1000, 4000, "主体分开", 4)])
    jobs.set_chunk_index_version(video_id, "index")
    jobs.update_job(video_id, state=JobState.ready, progress=100)
    jobs.save_visual_analysis(video_id, VisualAnalysisView(
        status="ready", version="sequence-v3", analyzed_at=datetime.now(UTC)))
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        system = body["messages"][0]["content"]
        if "event_index" in system:
            result = {"event_index": 0}
        elif "verdicts" in system:
            result = {"verdicts": [{"claim_id": "C1", "supported": True}]}
        elif "sections" in system:
            result = {"title": "主体变化", "sections": [{"heading": "事件", "text": "主体分开", "evidence_ids": ["E1"]}]}
        else:
            result = {"answerable": True, "claims": [{"text": "主体分开", "evidence_ids": ["E1"]}], "conversation_summary": "主体"}
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(result)}}]})

    generator = OpenAITextGenerator(base_url="https://example.test/v1", api_key="test-key",
                                    model="qwen-test", transport=httpx.MockTransport(handler))
    reader = FrameAnalyzer(generator)
    monkeypatch.setattr(reader, "_frame", lambda *_: b"\xff\xd8fake")
    service = GroundedGenerationService(jobs, conversations, EmptyRetriever(), generator,
                                         visual_reader=reader, data_root=tmp_path)
    return service, video_id, requests


@pytest.mark.parametrize("question", ["主要内容是什么？", "其中有哪些场景变化？请按出现顺序说明。"])
def test_overview_bypasses_empty_retrieval_and_verifies_against_raw_video(workflow, question):
    service, video_id, requests = workflow
    conversation = service.create_conversation(video_id)
    answer = service.ask(conversation.conversation_id, question)
    assert not answer.refused
    assert len(requests) == 2
    for request in requests:
        video = request["messages"][1]["content"][0]
        assert video["type"] == "video" and len(video["video"]) == 24
    assert service.generator.video_frames is None  # No request state leaks across users.


def test_detail_question_reopens_a_dense_local_window(workflow):
    service, video_id, requests = workflow
    answer = service.ask(service.create_conversation(video_id).conversation_id, "它是怎么分开的？")
    assert not answer.refused
    assert len(requests) == 3
    content = requests[1]["messages"][1]["content"]
    assert len([item for item in content if item["type"] == "image_url"]) == 24
    assert content[1]["text"] == "frame_timestamp_ms=0"
    assert content[-2]["text"] == "frame_timestamp_ms=7750"
    payload = json.loads(content[0]["text"].split("\n")[1])
    assert all("raw_video=true" in item["text"] for item in payload["evidence"])
    assert requests[2]["messages"][1]["content"][1]["text"] == "frame_timestamp_ms=0"


def test_detail_includes_lead_in_when_caption_only_locates_the_result(workflow):
    service, video_id, requests = workflow
    service.jobs.replace_chunks(video_id, [DocumentChunk(f"visual:{video_id}:result", 4100, 5100, "物体已分开", 5)])
    service.ask(service.create_conversation(video_id).conversation_id, "它是怎么分开的？")
    content = requests[1]["messages"][1]["content"]
    assert content[1]["text"] == "frame_timestamp_ms=100"
    assert content[-2]["text"] == "frame_timestamp_ms=7850"


def test_invalid_event_output_gets_one_bounded_retry(tmp_path, monkeypatch):
    reader = FrameAnalyzer(OpenAITextGenerator(base_url="https://example.test", api_key="test", model="test"))
    monkeypatch.setattr(reader, "_frame", lambda *_: b"\xff\xd8frame")
    calls = []
    def complete(**request):
        calls.append(request)
        if len(calls) == 1:
            return {"observations": [{"timestamp_ms": 0, "end_ms": 50000, "text": "越界"}]}
        return {"observations": [{"timestamp_ms": 0, "end_ms": 5000, "text": "已核对的事件"}]}
    monkeypatch.setattr(reader.generator, "_complete_json", complete)
    events = reader.analyze(tmp_path / "video.mp4", 6000, tmp_path / "frames")
    assert len(calls) == 2 and events[0].end_ms == 5000


def test_summary_cache_and_old_conversation_follow_analysis_revision(workflow):
    service, video_id, requests = workflow
    conversation = service.create_conversation(video_id)
    assert not service.summarize(video_id, SummaryRequest()).cached
    calls = len(requests)
    assert service.summarize(video_id, SummaryRequest()).cached
    assert len(requests) == calls
    analysis = service.jobs.get_visual_analysis(video_id)
    analysis.analyzed_at = datetime.now(UTC) + timedelta(seconds=1)
    service.jobs.save_visual_analysis(video_id, analysis)
    assert service.get_conversation(conversation.conversation_id).analysis_changed
    assert not service.summarize(video_id, SummaryRequest()).cached


def test_legacy_analysis_is_actionable_error_not_false_content_refusal(workflow):
    service, video_id, requests = workflow
    service.jobs.save_visual_analysis(video_id, VisualAnalysisView())
    with pytest.raises(ServiceError, match="VISION_ANALYSIS_REQUIRED"):
        service.ask(service.create_conversation(video_id).conversation_id, "主要内容是什么？")
    assert requests == []


def test_failed_visual_job_can_retry_without_losing_audio_warning(workflow):
    service, video_id, _ = workflow
    service.jobs.update_job(video_id, state=JobState.failed, progress=45)
    service.jobs.save_visual_analysis(video_id, VisualAnalysisView(status="failed", audio_warning="NO_AUDIO"))
    assert service.jobs.queue_visual_analysis(video_id)
    assert service.jobs.get_visual_analysis(video_id).audio_warning == "NO_AUDIO"
    assert not service.jobs.queue_visual_analysis(video_id)


def test_temporal_windows_overlap_and_cover_the_tail(tmp_path, monkeypatch):
    windows = []
    def handler(request):
        content = json.loads(request.content)["messages"][1]["content"]
        assert 4 <= len(content[0]["video"]) <= 24
        data = json.loads(content[1]["text"].split("\n")[-1])
        windows.append((data["start_ms"], data["end_ms"]))
        output = {"observations": [{"timestamp_ms": data["start_ms"], "end_ms": data["end_ms"], "text": "连续事件"}]}
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(output)}}]})
    reader = FrameAnalyzer(OpenAITextGenerator(base_url="https://example.test/v1", api_key="test",
                          model="qwen-test", transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(reader, "_frame", lambda *_: b"\xff\xd8frame")
    events = reader.analyze(tmp_path / "video.mp4", 30000, tmp_path / "frames")
    assert windows == [(0, 12000), (10000, 22000), (20000, 30000)]
    assert events[-1].end_ms == 30000
    # A retry after a later stage fails must reuse validated event checkpoints.
    reader.analyze(tmp_path / "video.mp4", 30000, tmp_path / "frames")
    assert len(windows) == 3


def test_sampling_avoids_nominal_eof_and_respects_dense_frame_budget(tmp_path, monkeypatch):
    reader = FrameAnalyzer(OpenAITextGenerator(base_url=None, api_key=None, model=None))
    timestamps = []
    def frame(_, time):
        timestamps.append(time)
        assert time <= 29_750
        return b"\xff\xd8frame"
    monkeypatch.setattr(reader, "_frame", frame)
    result = reader.read(tmp_path / "camera.mp4", 24000, 30000, tmp_path / "frames", dense=True)
    assert len(result.frames) == 24
    assert timestamps[0] == 24000 and timestamps[-1] == 29750


def test_short_shot_is_not_lost_inside_a_long_window(tmp_path, monkeypatch):
    reader = FrameAnalyzer(OpenAITextGenerator(base_url=None, api_key=None, model=None), scene_detection=True)
    monkeypatch.setattr(reader, "_detect_scenes", lambda *_: [(0, 16500), (16500, 17500), (17500, 30000)])
    windows = reader.windows(tmp_path / "movie.mp4", 30000)
    assert (16500, 17500) in windows
    assert windows[0][0] == 0 and windows[-1][1] == 30000
    assert all(end - start <= 12000 for start, end in windows)


def test_scene_budget_fails_before_any_model_request(tmp_path, monkeypatch):
    reader = FrameAnalyzer(OpenAITextGenerator(base_url=None, api_key=None, model=None), scene_detection=True, max_windows=2)
    monkeypatch.setattr(reader, "_detect_scenes", lambda *_: [(0, 1000), (1000, 2000), (2000, 3000)])
    with pytest.raises(Exception, match="VISION_TOO_MANY_SCENES"):
        reader.windows(tmp_path / "movie.mp4", 3000)
