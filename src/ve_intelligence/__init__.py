"""VE Intelligence - Bedrock Knowledge Base retrieval layer."""

from .config import DEFAULT_KB_ID, DEFAULT_REGION
from .kb import (
    AgenticAnswer,
    Citation,
    KnowledgeBaseClient,
    RetrievedChunk,
    StreamEvent,
)

__all__ = [
    "AgenticAnswer",
    "Citation",
    "DEFAULT_KB_ID",
    "DEFAULT_REGION",
    "KnowledgeBaseClient",
    "RetrievedChunk",
    "StreamEvent",
]
