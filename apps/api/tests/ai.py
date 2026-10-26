"""A fake AI provider and ready-made versions for tests — no test ever calls a real provider.

- `fake_embedding(text)`: the vector the fake provider returns for `text` (deterministic, unit length).
- `FakeAi`: answers `POST …/embeddings` like the provider would and records each request (fixture `fake_ai`).
- `ready_version(admin_db, version_id, contents)`: turns an uploaded version into a `ready` one with these chunks and
  their fake embeddings, straight in the database (for search and assistant tests that need no PDF processing).
"""

import hashlib
import json
import math
from dataclasses import dataclass, field
from uuid import UUID

import httpx
from sqlalchemy import Text, delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.models.documents import EMBEDDING_DIMENSIONS, Document, DocumentVersion, ProcessingStatus, TextChunk


def fake_embedding(text: str) -> list[float]:
    """A unit vector seeded by the text: equal texts give equal vectors, different texts (almost) orthogonal ones."""
    seed = text.encode()
    stream = b"".join(
        hashlib.sha256(seed + block.to_bytes(4, "big")).digest() for block in range(EMBEDDING_DIMENSIONS // 8)
    )
    vector = [int.from_bytes(stream[i : i + 4], "big") / 2**31 - 1.0 for i in range(0, EMBEDDING_DIMENSIONS * 4, 4)]
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector]


@dataclass
class FakeAi:
    """The fake provider. Set `fail_status` to answer every request with that HTTP status, or `fail_after` to answer
    that many requests normally and fail the following ones (with `fail_status`, default 503)."""

    requests: list[httpx.Request] = field(default_factory=list[httpx.Request])
    fail_status: int | None = None
    fail_after: int | None = None
    dimensions: int = EMBEDDING_DIMENSIONS

    @property
    def inputs(self) -> list[list[str]]:
        """The texts of every request, in order."""
        return [json.loads(request.content)["input"] for request in self.requests]

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        failing = self.fail_after is not None and len(self.requests) > self.fail_after
        if self.fail_status is not None and (self.fail_after is None or failing):
            return httpx.Response(self.fail_status, json={"error": {"message": "fake failure"}})
        if failing:
            return httpx.Response(503, json={"error": {"message": "fake outage"}})
        texts: list[str] = json.loads(request.content)["input"]
        data = [
            {"object": "embedding", "index": index, "embedding": fake_embedding(text)[: self.dimensions]}
            for index, text in enumerate(texts)
        ]
        data.reverse()  # the provider does not promise the order; `index` does
        usage = {"prompt_tokens": len(texts) * 10, "total_tokens": len(texts) * 10}
        return httpx.Response(200, json={"object": "list", "data": data, "model": "fake", "usage": usage})


async def ready_version(admin_db: AsyncSession, version_id: UUID | str, contents: list[str]) -> list[TextChunk]:
    """Replace the version's chunks with one chunk per text (page 1, 2, …), each with its `fake_embedding`, and mark
    the version `ready` (page count = number of texts). No PDF is read and no provider is called."""
    version_id = UUID(str(version_id))
    language = await admin_db.scalar(
        select(Document.language)
        .join(DocumentVersion, DocumentVersion.document_id == Document.id)
        .where(DocumentVersion.id == version_id)
    )
    assert language is not None, "unknown version"
    version = await admin_db.get_one(DocumentVersion, version_id)
    ts_config = await admin_db.scalar(select(func.ts_config_for_language(language).cast(Text)))
    await admin_db.execute(delete(TextChunk).where(TextChunk.version_id == version_id))
    await admin_db.execute(
        insert(TextChunk),
        [
            {
                "tenant_id": version.tenant_id,
                "version_id": version_id,
                "page_no": index + 1,
                "chunk_index": index,
                "content": content,
                "ts_config": ts_config,
                "embedding": fake_embedding(content),
            }
            for index, content in enumerate(contents)
        ],
    )
    version.processing_status = ProcessingStatus.READY
    version.processing_error = None
    version.page_count = len(contents)
    version.processed_at = func.now()
    await admin_db.commit()
    statement = select(TextChunk).where(TextChunk.version_id == version_id).order_by(TextChunk.chunk_index)
    return list(await admin_db.scalars(statement.execution_options(populate_existing=True)))
