from pathlib import Path
from uuid import uuid4

import pytest

from listen_dragon.domain.models import JobState, SummaryFormat, SummaryRequest
from listen_dragon.infrastructure.sqlite_conversations import (
    ConversationConflictError,
    SqliteConversationRepository,
)
from listen_dragon.infrastructure.sqlite_jobs import SqliteJobRepository
from listen_dragon.services.contracts import DocumentChunk, RetrievedChunk
from listen_dragon.services.grounded_generation import (
    GroundedGenerationService,
    ServiceError,
    format_timestamp_range,
)
from listen_dragon.services.llm_generation import (
    AnswerDraft,
    GroundedClaim,
    SummaryDraft,
    SummarySection,
)
from listen_dragon.services.retrieval import RetrievalError


class FakeRetriever:
    def __init__(self, chunks):
        self.chunks = chunks
        self.queries = []

    def search(self, video_id, query, limit=6):
        self.queries.append((video_id, query, limit))
        return self.chunks


class FakeGenerator:
    def __init__(self, *, answerable=True, supported=True):
        self.answerable = answerable
        self.supported = supported
        self.summary_calls = 0
        self.synthesis_calls = 0
        self.answer_calls = 0

    def answer(self, *, question, conversation_summary, evidence):
        self.answer_calls += 1
        memory = f"主题：{question}"[:1200]
        if not self.answerable:
            return AnswerDraft(False, (), memory)
        return AnswerDraft(
            True,
            (GroundedClaim("结论 [99:99] 有依据。", (evidence[0].chunk_id,)),),
            memory,
        )

    def summarize(self, *, evidence, language, length, format):
        self.summary_calls += 1
        return SummaryDraft(
            "视频主题",
            (SummarySection("要点", f"共 {len(evidence)} 个片段", (evidence[0].chunk_id,)),),
        )

    def verify(self, *, question, claims, evidence):
        return tuple(self.supported for _ in claims)

    def synthesize(self, *, drafts, evidence, language, length, format):
        self.synthesis_calls += 1
        return SummaryDraft(
            "全局摘要",
            (
                SummarySection(
                    "总览",
                    "分批内容已整合",
                    tuple(draft.sections[0].evidence_ids[0] for draft in drafts),
                ),
            ),
        )


@pytest.fixture
def ready_context(tmp_path: Path):
    database = tmp_path / "listen.db"
    jobs = SqliteJobRepository(database)
    jobs.initialize()
    conversations = SqliteConversationRepository(database)
    conversations.initialize()
    video_id = uuid4()
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")
    jobs.create_video_job(
        video_id=video_id,
        original_name="video.mp4",
        mime="video/mp4",
        size_bytes=5,
        sha256="0" * 64,
        source_path=source,
    )
    chunks = [
        DocumentChunk("a", 1000, 5000, "第一段内容" * 10, 10),
        DocumentChunk("b", 61000, 65000, "第二段内容" * 10, 10),
    ]
    jobs.replace_chunks(video_id, chunks)
    jobs.set_chunk_index_version(video_id, "a" * 16)
    jobs.update_job(video_id, state=JobState.ready, progress=100)
    return jobs, conversations, video_id


def make_service(ready_context, *, answerable=True, context_chars=24000):
    jobs, conversations, _ = ready_context
    retriever = FakeRetriever([RetrievedChunk("a", 1000, 5000, "第一段内容", 0.1)])
    generator = FakeGenerator(answerable=answerable)
    return (
        GroundedGenerationService(
            jobs, conversations, retriever, generator, context_chars=context_chars
        ),
        retriever,
        generator,
    )


def test_visual_and_speech_evidence_remain_distinct_in_answers_and_summary_cache(ready_context):
    jobs, conversations, video_id = ready_context
    visual = DocumentChunk(f"visual:{video_id}:4000", 4000, 5000, "画面观察：西瓜分成两半", 10)
    speech = DocumentChunk("speech", 1000, 8000, "疼吗", 2)
    jobs.replace_chunks(video_id, [speech])
    jobs.set_chunk_index_version(video_id, "old-index")
    generator = FakeGenerator()
    service = GroundedGenerationService(jobs, conversations, FakeRetriever([
        RetrievedChunk(visual.chunk_id, 4000, 5000, visual.text, 1),
    ]), generator)
    assert service.summarize(video_id, SummaryRequest()).cached is False
    jobs.replace_chunks(video_id, [visual, speech])
    jobs.set_chunk_index_version(video_id, "visual-index")
    assert service.summarize(video_id, SummaryRequest()).cached is False
    assert generator.summary_calls == 2
    created = service.create_conversation(video_id)
    result = service.ask(created.conversation_id, "画面中有什么？")
    assert result.evidence[0].source_type == "visual"
    assert result.evidence[0].start_ms == 4000
    restored = service.get_conversation(created.conversation_id)
    assert restored.messages[-1].evidence[0].source_type == "visual"


def test_overview_includes_visual_timeline_missed_by_nearest_chunk_retrieval(ready_context):
    jobs, conversations, video_id = ready_context
    visual = DocumentChunk(f"visual:{video_id}:4000", 4000, 5000, "画面中西瓜分成两半", 10)
    jobs.replace_chunks(video_id, jobs.list_chunks(video_id) + [visual])
    jobs.set_chunk_index_version(video_id, "combined-index")
    class OverviewGenerator(FakeGenerator):
        def answer(self, *, question, conversation_summary, evidence):
            assert any(item.source_type == "visual" for item in evidence)
            assert any(item.source_type == "speech" for item in evidence)
            assert len(evidence) == 3
            return AnswerDraft(True, (GroundedClaim("可见西瓜", (visual.chunk_id,)),), "")
    service = GroundedGenerationService(jobs, conversations, FakeRetriever([
        RetrievedChunk("a", 1000, 5000, "第一段内容", 1),
    ]), OverviewGenerator())
    created = service.create_conversation(video_id)
    result = service.ask(created.conversation_id, "这个视频主要是关于什么的？")
    assert result.evidence[0].source_type == "visual"


def test_grounded_answer_builds_server_owned_timestamp_and_persists_exchange(ready_context):
    _, conversations, video_id = ready_context
    service, retriever, _ = make_service(ready_context)
    created = service.create_conversation(video_id)
    result = service.ask(created.conversation_id, "第一段讲什么？")

    assert result.refused is False
    assert "[00:01-00:05]" in result.answer
    assert "[99:99]" not in result.answer
    assert result.evidence[0].chunk_id == "a"
    messages = conversations.list_messages(created.conversation_id)
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[1].evidence[0].video_id == video_id

    service.ask(created.conversation_id, "那为什么？")
    assert "对话背景" in retriever.queries[-1][1]
    assert "主题：第一段讲什么？" in retriever.queries[-1][1]


def test_unanswerable_question_uses_fixed_refusal_and_no_evidence(ready_context):
    _, conversations, video_id = ready_context
    service, _, _ = make_service(ready_context, answerable=False)
    conversation = service.create_conversation(video_id)
    result = service.ask(conversation.conversation_id, "视频没说的问题")
    assert result.refused is True
    assert result.evidence == []
    assert "未找到足够依据" in result.answer
    assert conversations.list_messages(conversation.conversation_id)[1].evidence == ()


def test_claim_rejected_by_independent_verifier_becomes_safe_refusal(ready_context):
    jobs, conversations, video_id = ready_context
    retriever = FakeRetriever([RetrievedChunk("a", 1000, 5000, "第一段内容", 0.1)])
    service = GroundedGenerationService(
        jobs, conversations, retriever, FakeGenerator(supported=False)
    )
    conversation = service.create_conversation(video_id)
    result = service.ask(conversation.conversation_id, "问题")
    assert result.refused is True
    assert result.evidence == []


def test_summary_batches_synthesizes_and_then_hits_cache(ready_context):
    _, _, video_id = ready_context
    service, _, generator = make_service(ready_context, context_chars=150)
    first = service.summarize(video_id, SummaryRequest())
    second = service.summarize(video_id, SummaryRequest())
    assert first.cached is False
    assert second.cached is True
    assert first.summary == second.summary
    assert generator.summary_calls == 2
    assert generator.synthesis_calls == 1
    assert {item.chunk_id for item in first.evidence} == {"a", "b"}


def test_summary_fails_closed_when_verifier_rejects_every_section(ready_context):
    jobs, conversations, video_id = ready_context
    service = GroundedGenerationService(
        jobs, conversations, FakeRetriever([]), FakeGenerator(supported=False)
    )
    with pytest.raises(ServiceError, match="LLM_INVALID_RESPONSE"):
        service.summarize(video_id, SummaryRequest())


def test_conversation_requires_ready_video_and_detects_concurrent_update(ready_context):
    jobs, conversations, video_id = ready_context
    service, _, _ = make_service(ready_context)
    jobs.update_job(video_id, state=JobState.indexing, progress=90)
    with pytest.raises(ServiceError, match="VIDEO_NOT_READY"):
        service.create_conversation(video_id)
    jobs.update_job(video_id, state=JobState.ready, progress=100)
    stored = conversations.create_conversation(video_id)
    conversations.append_exchange(
        conversation_id=stored.conversation_id,
        expected_revision=0,
        question="Q1",
        answer="A1",
        evidence=[],
        memory_summary="memory",
    )
    with pytest.raises(ConversationConflictError):
        conversations.append_exchange(
            conversation_id=stored.conversation_id,
            expected_revision=0,
            question="Q2",
            answer="A2",
            evidence=[],
            memory_summary="stale",
        )


def test_unknown_conversation_is_not_found(ready_context):
    service, _, _ = make_service(ready_context)
    with pytest.raises(ServiceError, match="CONVERSATION_NOT_FOUND"):
        service.ask(uuid4(), "问题")


def test_empty_retrieval_refuses_without_calling_generator(ready_context):
    jobs, conversations, video_id = ready_context
    generator = FakeGenerator()
    service = GroundedGenerationService(jobs, conversations, FakeRetriever([]), generator)
    conversation = service.create_conversation(video_id)
    result = service.ask(conversation.conversation_id, "没有召回")
    assert result.refused is True
    assert generator.answer_calls == 0


def test_service_rejects_generator_citation_outside_retrieved_set(ready_context):
    jobs, conversations, video_id = ready_context

    class BadGenerator(FakeGenerator):
        def answer(self, **kwargs):
            return AnswerDraft(True, (GroundedClaim("结论", ("not-retrieved",)),), "")

        def verify(self, **kwargs):
            return (True,)

    service = GroundedGenerationService(
        jobs,
        conversations,
        FakeRetriever([RetrievedChunk("a", 1000, 5000, "证据", 0.1)]),
        BadGenerator(),
    )
    conversation = service.create_conversation(video_id)
    with pytest.raises(ServiceError, match="LLM_INVALID_RESPONSE"):
        service.ask(conversation.conversation_id, "问题")


def test_service_maps_late_conversation_conflict(ready_context, monkeypatch):
    _, conversations, video_id = ready_context
    service, _, _ = make_service(ready_context)
    conversation = service.create_conversation(video_id)

    def conflict(**kwargs):
        raise ConversationConflictError("stale")

    monkeypatch.setattr(conversations, "append_exchange", conflict)
    with pytest.raises(ServiceError, match="CONVERSATION_CONFLICT"):
        service.ask(conversation.conversation_id, "问题")


def test_summary_missing_index_and_unknown_video_are_explicit(ready_context, tmp_path):
    jobs, conversations, _ = ready_context
    service, _, _ = make_service(ready_context)
    with pytest.raises(ServiceError, match="VIDEO_NOT_FOUND"):
        service.create_conversation(uuid4())

    video_id = uuid4()
    source = tmp_path / "second.mp4"
    source.write_bytes(b"video")
    jobs.create_video_job(
        video_id=video_id,
        original_name="second.mp4",
        mime="video/mp4",
        size_bytes=5,
        sha256="1" * 64,
        source_path=source,
    )
    jobs.update_job(video_id, state=JobState.ready, progress=100)
    missing_index = GroundedGenerationService(
        jobs, conversations, FakeRetriever([]), FakeGenerator()
    )
    with pytest.raises(RetrievalError, match="INDEX_NOT_FOUND"):
        missing_index.summarize(video_id, SummaryRequest())


def test_paragraph_summary_and_hour_timestamp(ready_context):
    _, _, video_id = ready_context
    service, _, _ = make_service(ready_context)
    result = service.summarize(video_id, SummaryRequest(format=SummaryFormat.paragraphs))
    assert "要点：" in result.summary
    assert "## 要点" not in result.summary
    assert format_timestamp_range(3_661_000, 3_722_000) == "[01:01:01-01:02:02]"
