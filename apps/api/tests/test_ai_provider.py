"""The AI provider (ai/provider.py) and batching (ai/embeddings.py), against a fake HTTP transport — no network."""

import json
from collections.abc import Iterator

import httpx
import pytest

from seedoc.ai import provider
from seedoc.ai.embeddings import EMBED_BATCH_SIZE, batches
from seedoc.ai.provider import AiConfigurationError, AiUnavailableError, create_embeddings, is_ai_configured
from seedoc.config import get_settings
from tests.ai import FakeAi, fake_embedding

KEY = "sk-test-not-a-real-key"


@pytest.fixture
def configure(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Settings re-read after each `monkeypatch.setenv`; cleared again so later tests see the test defaults."""
    monkeypatch.setenv("AI_API_KEY", KEY)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _use(monkeypatch: pytest.MonkeyPatch, handler: FakeAi) -> FakeAi:
    monkeypatch.setattr(provider, "transport", httpx.MockTransport(handler.handle))
    return handler


def _set(monkeypatch: pytest.MonkeyPatch, **env: str) -> None:
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()


def test_ai_is_not_configured_without_a_key() -> None:
    assert is_ai_configured() is False


@pytest.mark.usefixtures("configure")
def test_ai_is_configured_with_a_key() -> None:
    assert is_ai_configured() is True


@pytest.mark.usefixtures("configure")
async def test_openai_request_shape_and_vectors_in_input_order(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _use(monkeypatch, FakeAi())

    result = await create_embeddings(["Filter wechseln", "Öl prüfen"])

    [request] = fake.requests
    assert str(request.url) == "https://api.openai.com/v1/embeddings"
    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert "api-key" not in request.headers
    assert json.loads(request.content) == {"model": "text-embedding-3-small", "input": ["Filter wechseln", "Öl prüfen"]}
    # The fake answers in reverse order; `index` puts them back.
    assert result.vectors == [fake_embedding("Filter wechseln"), fake_embedding("Öl prüfen")]
    assert result.total_tokens == 20


@pytest.mark.usefixtures("configure")
async def test_base_url_overrides_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _use(monkeypatch, FakeAi())
    _set(monkeypatch, AI_BASE_URL="https://eu.api.openai.com/v1/", EMBEDDING_MODEL="text-embedding-3-small")

    await create_embeddings(["a"])

    assert str(fake.requests[0].url) == "https://eu.api.openai.com/v1/embeddings"


@pytest.mark.usefixtures("configure")
async def test_azure_uses_the_api_key_header(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _use(monkeypatch, FakeAi())
    _set(monkeypatch, AI_PROVIDER="azure_openai", AI_BASE_URL="https://seedoc.openai.azure.com/openai/v1")

    await create_embeddings(["a"])

    [request] = fake.requests
    assert str(request.url) == "https://seedoc.openai.azure.com/openai/v1/embeddings"
    assert request.headers["api-key"] == KEY
    assert "authorization" not in request.headers


@pytest.mark.usefixtures("configure")
async def test_azure_needs_a_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _use(monkeypatch, FakeAi())
    _set(monkeypatch, AI_PROVIDER="azure_openai", AI_BASE_URL="")

    with pytest.raises(AiConfigurationError):
        await create_embeddings(["a"])
    assert fake.requests == []


@pytest.mark.usefixtures("configure")
async def test_mistral_default_url(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _use(monkeypatch, FakeAi())
    _set(monkeypatch, AI_PROVIDER="mistral")

    await create_embeddings(["a"])

    assert str(fake.requests[0].url) == "https://api.mistral.ai/v1/embeddings"
    assert fake.requests[0].headers["authorization"] == f"Bearer {KEY}"


@pytest.mark.usefixtures("configure")
@pytest.mark.parametrize("status", [429, 500, 502, 503])
async def test_rate_limits_and_server_errors_are_unavailable(monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    _use(monkeypatch, FakeAi(fail_status=status))

    with pytest.raises(AiUnavailableError):
        await create_embeddings(["a"])


@pytest.mark.usefixtures("configure")
async def test_network_errors_are_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    monkeypatch.setattr(provider, "transport", httpx.MockTransport(down))

    with pytest.raises(AiUnavailableError):
        await create_embeddings(["a"])


@pytest.mark.usefixtures("configure")
@pytest.mark.parametrize("status", [400, 401, 403, 404])
async def test_refused_requests_are_configuration_errors_without_the_key(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    _use(monkeypatch, FakeAi(fail_status=status))

    with pytest.raises(AiConfigurationError) as error:
        await create_embeddings(["geheimer Text"])

    assert KEY not in str(error.value)
    assert "geheimer Text" not in str(error.value)
    assert error.value.__cause__ is None


@pytest.mark.usefixtures("configure")
async def test_wrong_dimensions_are_a_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, FakeAi(dimensions=1024))  # e.g. mistral-embed

    with pytest.raises(AiConfigurationError):
        await create_embeddings(["a"])


@pytest.mark.usefixtures("configure")
async def test_a_short_or_broken_answer_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def short(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": fake_embedding("a")}]})

    def broken(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>proxy error</html>")

    for handler in (short, broken):
        monkeypatch.setattr(provider, "transport", httpx.MockTransport(handler))
        with pytest.raises(AiUnavailableError):
            await create_embeddings(["a", "b"])


def test_batches_of_96_in_order() -> None:
    items = list(range(2 * EMBED_BATCH_SIZE + 5))

    parts = batches(items)

    assert EMBED_BATCH_SIZE == 96
    assert [len(part) for part in parts] == [96, 96, 5]
    assert [item for part in parts for item in part] == items
    assert batches([]) == []
