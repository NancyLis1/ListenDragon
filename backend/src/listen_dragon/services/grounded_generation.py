from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from listen_dragon.domain.models import (
    AnswerView,
    ConversationCreated,
    ConversationMessageView,
    ConversationView,
    EvidenceView,
    JobState,
    SummaryRequest,
    SummaryView,
)
from listen_dragon.infrastructure.sqlite_conversations import (
    ConversationConflictError,
    SqliteConversationRepository,
)
from listen_dragon.infrastructure.sqlite_jobs import SqliteJobRepository
from listen_dragon.services.contracts import DocumentChunk, RetrievedChunk
from listen_dragon.services.llm_generation import (
    AnswerDraft,
    GroundedClaim,
    OpenAITextGenerator,
    SourceEvidence,
    SummaryDraft,
)
from listen_dragon.services.retrieval import RetrievalError

_MODEL_TIMESTAMP = re.compile(r"\[\d{1,2}:\d{2}(?::\d{2})?(?:-\d{1,2}:\d{2}(?::\d{2})?)?\]")
_REFUSAL = "视频中未找到足够依据。请尝试补充关键词、明确指代，或换一种问法。"


class Retriever(Protocol):
    def search(self, video_id: str, query: str, limit: int = 6) -> Sequence[RetrievedChunk]: ...


class TextGenerator(Protocol):
    def answer(
        self,
        *,
        question: str,
        conversation_summary: str,
        evidence: Sequence[SourceEvidence],
    ) -> AnswerDraft: ...

    def verify(
        self,
        *,
        question: str,
        claims: Sequence[GroundedClaim],
        evidence: Sequence[SourceEvidence],
    ) -> tuple[bool, ...]: ...

    def summarize(
        self,
        *,
        evidence: Sequence[SourceEvidence],
        language: str,
        length: str,
        format: str,
    ) -> SummaryDraft: ...

    def synthesize(
        self,
        *,
        drafts: Sequence[SummaryDraft],
        evidence: Sequence[SourceEvidence],
        language: str,
        length: str,
        format: str,
    ) -> SummaryDraft: ...


@dataclass(frozen=True)
class GroundedGenerationService:
    jobs: SqliteJobRepository
    conversations: SqliteConversationRepository
    retriever: Retriever
    generator: TextGenerator
    context_chars: int = 24000
    memory_chars: int = 1200

    def create_conversation(self, video_id: UUID) -> ConversationCreated:
        self._require_ready(video_id)
        stored = self.conversations.create_conversation(video_id)
        return ConversationCreated(
            conversation_id=stored.conversation_id,
            video_id=stored.video_id,
            created_at=stored.created_at,
        )

    def get_conversation(self, conversation_id: UUID) -> ConversationView:
        stored = self.conversations.get_conversation(conversation_id)
        if stored is None:
            raise ServiceError("CONVERSATION_NOT_FOUND")
        return ConversationView(
            conversation_id=stored.conversation_id,
            video_id=stored.video_id,
            created_at=stored.created_at,
            messages=[
                ConversationMessageView(
                    message_id=message.message_id,
                    role=message.role,
                    content=message.content,
                    evidence=list(message.evidence),
                    created_at=message.created_at,
                )
                for message in self.conversations.list_messages(conversation_id)
            ],
        )

    def ask(self, conversation_id: UUID, question: str) -> AnswerView:
        conversation = self.conversations.get_conversation(conversation_id)
        if conversation is None:
            raise ServiceError("CONVERSATION_NOT_FOUND")
        self._require_ready(conversation.video_id)
        retrieval_query = _contextual_query(question, conversation.memory_summary, max_chars=1000)
        chunks = self.retriever.search(str(conversation.video_id), retrieval_query, limit=6)
        sources = tuple(_from_retrieved(item) for item in chunks)
        if sources:
            draft = self.generator.answer(
                question=question,
                conversation_summary=conversation.memory_summary,
                evidence=sources,
            )
        else:
            draft = AnswerDraft(False, (), conversation.memory_summary)

        if draft.answerable:
            verdicts = self.generator.verify(
                question=question, claims=draft.claims, evidence=sources
            )
            supported_claims = tuple(
                claim for claim, supported in zip(draft.claims, verdicts, strict=True) if supported
            )
            draft = AnswerDraft(
                bool(supported_claims), supported_claims, draft.conversation_summary
            )

        if draft.answerable:
            by_id = {item.chunk_id: item for item in sources}
            cited_ids = tuple(
                dict.fromkeys(chunk_id for claim in draft.claims for chunk_id in claim.evidence_ids)
            )
            if any(chunk_id not in by_id for chunk_id in cited_ids):
                raise ServiceError("LLM_INVALID_RESPONSE")
            answer = "\n\n".join(
                _clean_generated_text(claim.text)
                + " "
                + " ".join(
                    format_timestamp_range(by_id[item].start_ms, by_id[item].end_ms)
                    for item in claim.evidence_ids
                )
                for claim in draft.claims
            )
            evidence = tuple(
                _evidence_view(conversation.video_id, by_id[chunk_id]) for chunk_id in cited_ids
            )
            refused = False
        else:
            answer = _REFUSAL
            evidence = ()
            refused = True

        memory = draft.conversation_summary[: self.memory_chars].strip()
        try:
            message = self.conversations.append_exchange(
                conversation_id=conversation_id,
                expected_revision=conversation.revision,
                question=question,
                answer=answer,
                evidence=evidence,
                memory_summary=memory,
            )
        except ConversationConflictError as exc:
            raise ServiceError("CONVERSATION_CONFLICT") from exc
        return AnswerView(
            conversation_id=conversation_id,
            message_id=message.message_id,
            answer=answer,
            refused=refused,
            evidence=list(evidence),
            created_at=message.created_at,
        )

    def summarize(self, video_id: UUID, options: SummaryRequest) -> SummaryView:
        self._require_ready(video_id)
        try:
            index_version = self.jobs.get_chunk_index_version(video_id)
        except ValueError as exc:
            raise RetrievalError("INDEX_VERSION_MISMATCH") from exc
        if index_version is None:
            raise RetrievalError("INDEX_NOT_FOUND")
        cached = self.conversations.get_summary(
            video_id=video_id,
            index_version=index_version,
            language=options.language.value,
            length=options.length.value,
            format=options.format.value,
        )
        if cached is not None:
            return SummaryView(
                video_id=video_id,
                summary=cached.content,
                evidence=list(cached.evidence),
                language=options.language,
                length=options.length,
                format=options.format,
                cached=True,
                generated_at=cached.generated_at,
            )

        chunks = self.jobs.list_chunks(video_id)
        if not chunks:
            raise RetrievalError("INDEX_NOT_FOUND")
        sources = tuple(_from_document(item) for item in chunks)
        batches = _partition_sources(sources, self.context_chars)
        drafts = [
            self.generator.summarize(
                evidence=batch,
                language=options.language.value,
                length=options.length.value,
                format=options.format.value,
            )
            for batch in batches
        ]
        draft = (
            drafts[0]
            if len(drafts) == 1
            else self.generator.synthesize(
                drafts=drafts,
                evidence=sources,
                language=options.language.value,
                length=options.length.value,
                format=options.format.value,
            )
        )
        draft = _verify_summary_draft(self.generator, draft, sources)
        content, evidence = _render_summary(video_id, draft, sources, options.format.value)
        stored = self.conversations.save_summary(
            video_id=video_id,
            index_version=index_version,
            language=options.language.value,
            length=options.length.value,
            format=options.format.value,
            content=content,
            evidence=evidence,
        )
        return SummaryView(
            video_id=video_id,
            summary=stored.content,
            evidence=list(stored.evidence),
            language=options.language,
            length=options.length,
            format=options.format,
            cached=False,
            generated_at=stored.generated_at,
        )

    def _require_ready(self, video_id: UUID) -> None:
        job = self.jobs.get_video_job(video_id)
        if job is None:
            raise ServiceError("VIDEO_NOT_FOUND")
        if job.state is not JobState.ready:
            raise ServiceError("VIDEO_NOT_READY")


class ServiceError(RuntimeError):
    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


def build_generation_service(
    *,
    jobs: SqliteJobRepository,
    conversations: SqliteConversationRepository,
    retriever: Retriever,
    generator: OpenAITextGenerator,
    context_chars: int,
    memory_chars: int,
) -> GroundedGenerationService:
    return GroundedGenerationService(
        jobs=jobs,
        conversations=conversations,
        retriever=retriever,
        generator=generator,
        context_chars=context_chars,
        memory_chars=memory_chars,
    )


def format_timestamp_range(start_ms: int, end_ms: int) -> str:
    return f"[{_format_time(start_ms)}-{_format_time(end_ms)}]"


def _format_time(milliseconds: int) -> str:
    total_seconds = max(0, milliseconds // 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _contextual_query(question: str, memory: str, *, max_chars: int) -> str:
    question = " ".join(question.split())
    if not memory.strip():
        return question
    suffix = "\n对话背景（仅用于消解指代）：「" + " ".join(memory.split()) + "」"
    return (question + suffix)[:max_chars]


def _from_retrieved(chunk: RetrievedChunk) -> SourceEvidence:
    return SourceEvidence(chunk.chunk_id, chunk.start_ms, chunk.end_ms, chunk.text)


def _from_document(chunk: DocumentChunk) -> SourceEvidence:
    return SourceEvidence(chunk.chunk_id, chunk.start_ms, chunk.end_ms, chunk.text)


def _partition_sources(
    sources: Sequence[SourceEvidence], max_chars: int
) -> tuple[tuple[SourceEvidence, ...], ...]:
    batches: list[tuple[SourceEvidence, ...]] = []
    current: list[SourceEvidence] = []
    current_size = 0
    for source in sources:
        item_size = len(source.text) + 120
        if current and current_size + item_size > max_chars:
            batches.append(tuple(current))
            current = []
            current_size = 0
        current.append(source)
        current_size += item_size
    if current:
        batches.append(tuple(current))
    return tuple(batches)


def _render_summary(
    video_id: UUID,
    draft: SummaryDraft,
    sources: Sequence[SourceEvidence],
    format: str,
) -> tuple[str, tuple[EvidenceView, ...]]:
    by_id = {item.chunk_id: item for item in sources}
    cited_ids: list[str] = []
    rendered_sections: list[str] = []
    for section in draft.sections:
        if any(item not in by_id for item in section.evidence_ids):
            raise ServiceError("LLM_INVALID_RESPONSE")
        cited_ids.extend(section.evidence_ids)
        citations = " ".join(
            format_timestamp_range(by_id[item].start_ms, by_id[item].end_ms)
            for item in section.evidence_ids
        )
        text = _clean_generated_text(section.text)
        if format == "outline":
            rendered_sections.append(
                f"## {_clean_generated_text(section.heading)}\n{text} {citations}"
            )
        else:
            rendered_sections.append(
                f"{_clean_generated_text(section.heading)}：{text} {citations}"
            )
    title = _clean_generated_text(draft.title)
    content = f"# {title}\n\n" + "\n\n".join(rendered_sections)
    evidence = tuple(_evidence_view(video_id, by_id[item]) for item in dict.fromkeys(cited_ids))
    return content, evidence


def _verify_summary_draft(
    generator: TextGenerator,
    draft: SummaryDraft,
    sources: Sequence[SourceEvidence],
) -> SummaryDraft:
    cited_ids = {chunk_id for section in draft.sections for chunk_id in section.evidence_ids}
    cited_sources = tuple(source for source in sources if source.chunk_id in cited_ids)
    claims = tuple(
        GroundedClaim(f"{section.heading}：{section.text}", section.evidence_ids)
        for section in draft.sections
    )
    verdicts = generator.verify(
        question="核验这些视频摘要要点是否由各自引用的转写直接支持。",
        claims=claims,
        evidence=cited_sources,
    )
    sections = tuple(
        section for section, supported in zip(draft.sections, verdicts, strict=True) if supported
    )
    if not sections:
        raise ServiceError("LLM_INVALID_RESPONSE")
    return SummaryDraft(draft.title, sections)


def _evidence_view(video_id: UUID, source: SourceEvidence) -> EvidenceView:
    return EvidenceView(
        chunk_id=source.chunk_id,
        video_id=video_id,
        start_ms=source.start_ms,
        end_ms=source.end_ms,
        timestamp=format_timestamp_range(source.start_ms, source.end_ms),
        text=source.text,
    )


def _clean_generated_text(text: str) -> str:
    return _MODEL_TIMESTAMP.sub("", text).strip()
