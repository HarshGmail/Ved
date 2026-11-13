from decimal import Decimal

from ved_backend.llm.base import ModelUsage
from ved_backend.llm.pricing import cost_usd

HAIKU = "claude-haiku-5-5"


def test_standard_rates_price_each_kind_of_token_per_million():
    usage = ModelUsage(
        model=HAIKU,
        input_tokens=2_000,
        cache_creation_input_tokens=1_000,
        cache_read_input_tokens=10_000,
        output_tokens=500,
    )

    assert cost_usd(HAIKU, usage) == Decimal("0.000675")


def test_a_long_prompt_uses_the_higher_rates_for_every_kind_of_token():
    usage = ModelUsage(model=HAIKU, input_tokens=150_000, output_tokens=1_000)

    assert cost_usd(HAIKU, usage) == Decimal("0.077500")


def test_prompt_size_counts_cache_writes_and_reads_for_the_tier():
    usage = ModelUsage(
        model=HAIKU,
        input_tokens=2,
        cache_creation_input_tokens=50_000,
        cache_read_input_tokens=60_000,
    )

    assert cost_usd(HAIKU, usage) == Decimal("0.034251")


def test_a_prompt_of_exactly_100000_tokens_is_still_standard():
    usage = ModelUsage(model=HAIKU, input_tokens=100_000)

    assert cost_usd(HAIKU, usage) == Decimal("0.010000")


def test_one_token_over_100000_switches_to_the_long_prompt_rates():
    usage = ModelUsage(model=HAIKU, input_tokens=100_002)

    assert cost_usd(HAIKU, usage) == Decimal("0.050001")


def test_an_unknown_model_has_no_price():
    usage = ModelUsage(model="some-other-model", input_tokens=1_000)

    assert cost_usd("some-other-model", usage) is None


def test_missing_token_counts_are_read_as_zero():
    usage = ModelUsage(
        model=HAIKU,
        input_tokens=None,
        cache_creation_input_tokens=None,
        cache_read_input_tokens=None,
        output_tokens=None,
    )

    assert usage.input_tokens == 0
    assert usage.output_tokens == 0
    assert cost_usd(HAIKU, usage) == Decimal("0.000000")
