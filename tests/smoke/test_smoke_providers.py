"""Smoke tests — hit real provider APIs. Skipped by default.

Run with: python -m pytest -m live
"""

import os
import pytest

pytestmark = pytest.mark.live

STARRY_KEY = os.environ.get("STARRY_API_KEY", "")


@pytest.mark.skipif(not STARRY_KEY, reason="STARRY_API_KEY not set")
async def test_davy_list_models():
    """Smoke: DavyAI /models returns non-empty list."""
    from starry_lib.config.settings import load_settings
    from starry_lib.llm.client import list_models

    settings = load_settings()
    provider = settings.providers["davy"]
    models = await list_models(provider)
    assert len(models) > 0, "Expected at least one model from DavyAI"
    print(f"\nDavyAI models: {models}")


@pytest.mark.skipif(not STARRY_KEY, reason="STARRY_API_KEY not set")
async def test_davy_single_completion():
    """Smoke: DavyAI returns a non-empty response to 'say hi'."""
    from starry_lib.config.settings import load_settings
    from starry_lib.llm.client import build_client

    settings = load_settings()
    provider = settings.providers["davy"]
    client = build_client(provider)
    response = await client.chat.completions.create(
        model=provider.default_model,
        messages=[{"role": "user", "content": "Say hi briefly."}],
        max_tokens=20,
    )
    content = response.choices[0].message.content
    assert content and len(content) > 0
    print(f"\nDavyAI response: {content!r}")
