"""LLM client factory and model listing for StarryLib."""

import asyncio

import httpx
import openai
from openai import AsyncOpenAI

from starry_lib.config.settings import ProviderConfig


async def call_with_retry(
    factory,
    max_attempts: int = 3,
    delays: tuple = (1, 2, 4),
):
    """Call factory() with exponential backoff.

    Retries on RateLimitError (429) and server errors
    (5xx). Other errors are re-raised immediately.
    """
    last_exc: Exception | None = None
    for i in range(max_attempts):
        try:
            result = await factory()
            if result is None:
                raise RuntimeError(
                    "Provider returned an empty response "
                    "(null). The model may not support "
                    "the requested feature (e.g. tools)."
                )
            return result
        except openai.RateLimitError as exc:
            last_exc = exc
        except openai.APIStatusError as exc:
            if exc.status_code >= 500:
                last_exc = exc
            else:
                raise
        if i < max_attempts - 1:
            await asyncio.sleep(delays[i])
    raise last_exc  # type: ignore[misc]


def build_client(provider: ProviderConfig) -> AsyncOpenAI:
    """Build an AsyncOpenAI client from a ProviderConfig.

    Uses a custom httpx.AsyncClient when ssl_verify is not True
    (i.e. False or a cert path string).
    """
    api_key = provider.api_key  # raises RuntimeError if unset
    ssl_value = provider.ssl_verify_value

    if ssl_value is not True:
        http_client = httpx.AsyncClient(verify=ssl_value)
        return AsyncOpenAI(
            base_url=provider.base_url,
            api_key=api_key,
            http_client=http_client,
        )

    return AsyncOpenAI(
        base_url=provider.base_url,
        api_key=api_key,
    )


async def list_models(provider: ProviderConfig) -> list[str]:
    """Return a sorted list of model IDs from the provider.

    Returns an empty list on any error — never raises.
    """
    try:
        client = build_client(provider)
        response = await client.models.list()
        return sorted(m.id for m in response.data)
    except Exception:  # noqa: BLE001
        return []


_CONTEXT_WINDOW_FIELDS = (
    "context_length",
    "context_window",
    "max_context_length",
    "max_model_len",
)


async def get_model_context_window(
    provider: ProviderConfig, model_id: str
) -> int | None:
    """Try to get the context window size for *model_id*.

    Queries the provider's model list and inspects
    provider-specific extra fields (e.g. OpenRouter's
    ``context_length``).  Returns None if the information
    is unavailable or on any error — never raises.
    """
    try:
        client = build_client(provider)
        response = await client.models.list()
        for m in response.data:
            if m.id != model_id:
                continue
            extra = getattr(m, "model_extra", {}) or {}
            for field in _CONTEXT_WINDOW_FIELDS:
                val = extra.get(field)
                if isinstance(val, int) and val > 0:
                    return val
    except Exception:  # noqa: BLE001
        pass
    return None
