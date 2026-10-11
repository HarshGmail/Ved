import pytest

from ved_web.config import DEFAULT_SEARCH_PROVIDER, Settings
from ved_web.search import (
    PROVIDER_NAMES,
    SEARXNG,
    UnknownSearchProviderError,
    build_search_provider,
)
from ved_web.search.providers.searxng import (
    LOCAL_URL,
    SearxngProvider,
    SearxngSettings,
)


async def built(settings: Settings):
    provider = build_search_provider(settings)
    await provider.aclose()
    return provider


def test_searxng_is_the_default_provider():
    assert DEFAULT_SEARCH_PROVIDER == SEARXNG
    assert Settings(_env_file=None).search_provider == SEARXNG


async def test_the_default_settings_build_searxng(monkeypatch):
    monkeypatch.delenv("VED_SEARCH_PROVIDER", raising=False)
    monkeypatch.delenv("VED_SEARXNG_URL", raising=False)

    provider = await built(Settings(_env_file=None))

    assert isinstance(provider, SearxngProvider)
    assert provider._base_url == LOCAL_URL


@pytest.mark.parametrize("name", ["searxng", "SearXNG", " searxng "])
async def test_an_explicit_provider_name_is_matched_loosely(name):
    provider = await built(Settings(_env_file=None, search_provider=name))

    assert isinstance(provider, SearxngProvider)


async def test_the_provider_is_chosen_by_environment(monkeypatch):
    monkeypatch.setenv("VED_SEARCH_PROVIDER", "searxng")
    monkeypatch.setenv("VED_SEARXNG_URL", "http://search.internal:9999/")

    provider = await built(Settings(_env_file=None))

    assert isinstance(provider, SearxngProvider)
    assert provider._base_url == "http://search.internal:9999"


def test_an_unknown_provider_fails_naming_the_valid_ones():
    with pytest.raises(UnknownSearchProviderError) as raised:
        build_search_provider(Settings(_env_file=None, search_provider="altavista"))

    message = str(raised.value)
    assert "'altavista'" in message
    assert "VED_SEARCH_PROVIDER" in message
    assert all(name in message for name in PROVIDER_NAMES)


def test_another_providers_settings_in_env_file_do_not_break_startup(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "VED_SEARCH_PROVIDER=searxng\n"
        "VED_SEARXNG_URL=http://search.internal:9999\n"
        "VED_BRAVE_API_KEY=not-read-by-anyone-yet\n"
    )

    assert Settings(_env_file=env_file).search_provider == SEARXNG
    assert SearxngSettings(_env_file=env_file).url == "http://search.internal:9999"
