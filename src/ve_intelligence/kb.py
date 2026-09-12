"""Bedrock Knowledge Base access layer.

Wraps two bedrock-agent-runtime operations:

* ``retrieve``                -- single-shot lookup, returns raw chunks.
* ``agentic_retrieve_stream`` -- agent-driven multi-step retrieval with a
  streamed, generated answer plus planning traces.

The module is UI-agnostic on purpose. ``ask_stream`` yields plain
:class:`StreamEvent` objects so a CLI, Streamlit app, or FastAPI/SSE endpoint
can all consume the same code path.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Iterator, Literal
from urllib.parse import unquote, urlparse

import boto3
from botocore.config import Config

from .config import (
    DEFAULT_FOUNDATION_MODEL_TYPE,
    DEFAULT_KB_ID,
    DEFAULT_MAX_AGENT_ITERATION,
    DEFAULT_REGION,
)

EventKind = Literal["token", "trace", "result", "citation"]


def _decode_uri(uri: str) -> str:
    """S3 URIs come back percent-encoded, unreadable for Chinese filenames."""
    path = urlparse(uri).path
    return unquote(path).lstrip("/") or unquote(uri)


def _pretty_source(location: dict[str, Any], metadata: dict[str, Any] | None = None) -> str:
    """Turn a KB result into a human-readable source name.

    ``retrieve`` returns a ``location`` blob, while ``agentic_retrieve_stream``
    omits it and carries the document identity in ``metadata`` instead. Handle
    both so the UI always has a label to show.
    """
    location = location or {}

    s3_uri = (location.get("s3Location") or {}).get("uri")
    if s3_uri:
        return _decode_uri(s3_uri)

    for key in ("webLocation", "confluenceLocation", "salesforceLocation", "sharePointLocation"):
        url = (location.get(key) or {}).get("url")
        if url:
            return unquote(url)

    custom = (location.get("customDocumentLocation") or {}).get("id")
    if custom:
        return custom

    # Agentic path: fall back to the metadata fields.
    meta = metadata or {}
    title = meta.get("_document_title") or meta.get("title")
    if title:
        return str(title)
    for key in ("_source_uri", "_document_id", "source", "uri"):
        value = meta.get(key)
        if value:
            return _decode_uri(str(value))

    return location.get("type") or "unknown"


@dataclass(slots=True)
class RetrievedChunk:
    """One retrieved passage."""

    text: str
    source: str
    score: float | None = None
    location: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, item: dict[str, Any]) -> "RetrievedChunk":
        location = item.get("location") or {}
        metadata = item.get("metadata") or {}
        return cls(
            text=(item.get("content") or {}).get("text") or "",
            source=_pretty_source(location, metadata),
            score=item.get("score"),
            location=location,
            metadata=metadata,
        )

    def preview(self, limit: int = 240) -> str:
        flat = " ".join(self.text.split())
        return flat if len(flat) <= limit else flat[: limit - 1] + "…"


@dataclass(slots=True)
class Citation:
    """A ``[n]`` marker in the generated answer mapped back to its source."""

    index: int
    source: str
    text: str


@dataclass(slots=True)
class StreamEvent:
    """Normalised event emitted while an agentic query runs."""

    kind: EventKind
    text: str = ""
    step: str | None = None
    status: str | None = None
    chunks: list[RetrievedChunk] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgenticAnswer:
    """Fully materialised result of an agentic query."""

    answer: str
    chunks: list[RetrievedChunk] = field(default_factory=list)
    traces: list[StreamEvent] = field(default_factory=list)

    @property
    def citations(self) -> list[Citation]:
        """Sources in retrieval order, numbered to match ``[n]`` markers."""
        return [
            Citation(index=i, source=chunk.source, text=chunk.text)
            for i, chunk in enumerate(self.chunks, start=1)
        ]

    @property
    def sources(self) -> list[str]:
        """Unique source documents, order preserved."""
        seen: dict[str, None] = {}
        for chunk in self.chunks:
            seen.setdefault(chunk.source, None)
        return list(seen)


class KnowledgeBaseClient:
    """Thin, typed wrapper around the VE Intelligence knowledge base.

    Credentials resolve through the standard boto3 chain, so the ``[default]``
    profile in ``~/.aws/credentials`` is picked up with no profile name needed.
    """

    def __init__(
        self,
        knowledge_base_id: str = DEFAULT_KB_ID,
        region_name: str = DEFAULT_REGION,
        *,
        session: boto3.Session | None = None,
        read_timeout: int = 300,
    ) -> None:
        self.knowledge_base_id = knowledge_base_id
        self.region_name = region_name
        self._session = session or boto3.Session()
        # Agentic retrieval can plan for a while before the first token lands.
        self._client = self._session.client(
            "bedrock-agent-runtime",
            region_name=region_name,
            config=Config(read_timeout=read_timeout, retries={"max_attempts": 3, "mode": "standard"}),
        )

    # ------------------------------------------------------------------ #
    # Single-shot retrieval
    # ------------------------------------------------------------------ #
    def retrieve(self, query: str, *, max_results: int | None = None) -> list[RetrievedChunk]:
        """Plain vector lookup. No LLM, no planning -- fast and cheap.

        Note: this is a *managed* knowledge base, so ``vectorSearchConfiguration``
        is rejected by the API. Result count is tuned via
        ``managedSearchConfiguration`` instead.
        """
        request: dict[str, Any] = {
            "knowledgeBaseId": self.knowledge_base_id,
            "retrievalQuery": {"text": query},
        }
        if max_results is not None:
            request["retrievalConfiguration"] = {
                "managedSearchConfiguration": {"numberOfResults": max_results}
            }

        response = self._client.retrieve(**request)
        return [RetrievedChunk.from_api(item) for item in response.get("retrievalResults", [])]

    # ------------------------------------------------------------------ #
    # Agentic retrieval
    # ------------------------------------------------------------------ #
    def ask_stream(
        self,
        query: str,
        *,
        history: Iterable[dict[str, str]] | None = None,
        generate_response: bool = True,
        max_agent_iteration: int = DEFAULT_MAX_AGENT_ITERATION,
        foundation_model_type: str = DEFAULT_FOUNDATION_MODEL_TYPE,
    ) -> Iterator[StreamEvent]:
        """Run agentic retrieval, yielding events as they arrive.

        ``history`` accepts prior turns as ``{"role": ..., "text": ...}`` dicts
        so the UI can hold a multi-turn conversation.
        """
        messages: list[dict[str, Any]] = []
        for turn in history or []:
            messages.append({"role": turn["role"], "content": {"text": turn["text"]}})
        messages.append({"role": "user", "content": {"text": query}})

        response = self._client.agentic_retrieve_stream(
            messages=messages,
            retrievers=[
                {"configuration": {"knowledgeBase": {"knowledgeBaseId": self.knowledge_base_id}}}
            ],
            agenticRetrieveConfiguration={
                "foundationModelType": foundation_model_type,
                "maxAgentIteration": max_agent_iteration,
            },
            generateResponse=generate_response,
        )

        for event in response["stream"]:
            if "responseEvent" in event:
                text = event["responseEvent"].get("text", "")
                if text:
                    yield StreamEvent(kind="token", text=text, raw=event)

            elif "traceEvent" in event:
                attrs = event["traceEvent"].get("attributes", {}) or {}
                yield StreamEvent(
                    kind="trace",
                    text=str(attrs.get("message") or ""),
                    step=attrs.get("step"),
                    status=attrs.get("status"),
                    raw=event,
                )

            elif "result" in event:
                payload = event["result"]
                chunks = [RetrievedChunk.from_api(i) for i in payload.get("results", []) or []]
                generated = payload.get("generatedResponse") or ""
                yield StreamEvent(kind="result", text=generated, chunks=chunks, raw=event)

            else:
                # Forward anything new the API starts sending rather than dropping it.
                yield StreamEvent(kind="trace", text=f"unhandled event: {list(event)}", raw=event)

    def ask(
        self,
        query: str,
        *,
        history: Iterable[dict[str, str]] | None = None,
        on_token: Callable[[str], None] | None = None,
        on_trace: Callable[[StreamEvent], None] | None = None,
        max_agent_iteration: int = DEFAULT_MAX_AGENT_ITERATION,
    ) -> AgenticAnswer:
        """Blocking convenience wrapper that collects the whole stream.

        Pass ``on_token`` to still get live output while collecting.
        """
        parts: list[str] = []
        chunks: list[RetrievedChunk] = []
        traces: list[StreamEvent] = []
        final_answer = ""

        for event in self.ask_stream(
            query, history=history, max_agent_iteration=max_agent_iteration
        ):
            if event.kind == "token":
                parts.append(event.text)
                if on_token:
                    on_token(event.text)
            elif event.kind == "trace":
                traces.append(event)
                if on_trace:
                    on_trace(event)
            elif event.kind == "result":
                chunks = event.chunks
                final_answer = event.text

        # The streamed tokens are authoritative; fall back to the result blob.
        answer = "".join(parts).strip() or final_answer.strip()
        return AgenticAnswer(answer=answer, chunks=chunks, traces=traces)


def default_client() -> KnowledgeBaseClient:
    """Client built from environment/config defaults."""
    return KnowledgeBaseClient(
        knowledge_base_id=os.getenv("VE_KB_ID", DEFAULT_KB_ID),
        region_name=os.getenv("VE_AWS_REGION", DEFAULT_REGION),
    )
