"""The AI provider (ARCHITECTURE §3, D13): every call to an AI service goes through this module.

One HTTP shape for all three providers: `POST {base}/embeddings` with `{"model", "input"}`, answered with
`{"data": [{"index", "embedding"}], "usage": {"total_tokens"}}`. Only the base URL and the auth header differ:

- `openai`: `https://api.openai.com/v1` (or `AI_BASE_URL`, e.g. the EU endpoint), `Authorization: Bearer`.
- `azure_openai`: `AI_BASE_URL` = `https://<resource>.openai.azure.com/openai/v1` (required), header `api-key`.
- `mistral`: `https://api.mistral.ai/v1` (or `AI_BASE_URL`), `Authorization: Bearer`.

Never logged or put into an error: the API key, the texts, the response body (it can echo the input).
"""

from dataclasses import dataclass

import httpx
import structlog

from seedoc.config import AiProvider, get_settings
from seedoc.models.documents import EMBEDDING_DIMENSIONS

log = structlog.get_logger()

_DEFAULT_BASE_URLS = {
    AiProvider.OPENAI: "https://api.openai.com/v1",
    AiProvider.MISTRAL: "https://api.mistral.ai/v1",
}
TIMEOUT_SECONDS = 60.0

# Tests replace it with an `httpx.MockTransport`, so no test ever reaches a real provider.
transport: httpx.AsyncBaseTransport | None = None


class AiUnavailableError(Exception):
    """The provider did not answer usefully (time-out, network, 429, 5xx): worth retrying later."""


class AiConfigurationError(Exception):
    """The provider refused the request (bad key, unknown model, wrong dimensions): retrying will not help."""


@dataclass(frozen=True)
class Embeddings:
    vectors: list[list[float]]  # one per input text, in input order
    total_tokens: int


def is_ai_configured() -> bool:
    """False without `AI_API_KEY` (local, CI, staging until a key exists); production refuses to start then."""
    return get_settings().ai_api_key != ""


async def create_embeddings(texts: list[str]) -> Embeddings:
    """Embed `texts` (one request; the caller batches) with `EMBEDDING_MODEL`."""
    settings = get_settings()
    base_url = settings.ai_base_url.rstrip("/") or _DEFAULT_BASE_URLS.get(settings.ai_provider, "")
    if base_url == "":
        raise AiConfigurationError(f"AI_BASE_URL is required for {settings.ai_provider}")
    headers = (
        {"api-key": settings.ai_api_key}
        if settings.ai_provider is AiProvider.AZURE_OPENAI
        else {"Authorization": f"Bearer {settings.ai_api_key}"}
    )
    try:
        async with httpx.AsyncClient(transport=transport, timeout=TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{base_url}/embeddings", headers=headers, json={"model": settings.embedding_model, "input": texts}
            )
    except httpx.HTTPError as exc:
        raise AiUnavailableError(type(exc).__name__) from None
    if response.status_code == 429 or response.status_code >= 500:
        raise AiUnavailableError(f"HTTP {response.status_code}")
    if response.status_code != 200:
        raise AiConfigurationError(f"HTTP {response.status_code}")
    return _parse_embeddings(response, len(texts))


def _parse_embeddings(response: httpx.Response, expected: int) -> Embeddings:
    try:
        body = response.json()
        items = sorted(body["data"], key=lambda item: item["index"])
        vectors: list[list[float]] = [[float(x) for x in item["embedding"]] for item in items]
        total_tokens = int(body.get("usage", {}).get("total_tokens", 0))
    except (ValueError, KeyError, TypeError):
        raise AiUnavailableError("unexpected response") from None
    if len(vectors) != expected:
        raise AiUnavailableError(f"{len(vectors)} embeddings for {expected} texts")
    if any(len(vector) != EMBEDDING_DIMENSIONS for vector in vectors):
        # The column is vector(1536); another model (e.g. mistral-embed, 1024) needs a migration first.
        raise AiConfigurationError(f"the model does not return {EMBEDDING_DIMENSIONS} dimensions")
    return Embeddings(vectors=vectors, total_tokens=total_tokens)
