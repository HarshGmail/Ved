from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from ved_backend.llm.base import ModelUsage

TOKENS_PER_MILLION = Decimal(1_000_000)
MICRO_USD = Decimal("0.000001")
LONG_PROMPT_THRESHOLD_TOKENS = 100_000
CLAUDE_HAIKU_5_5 = "claude-haiku-5-5"


@dataclass(frozen=True)
class TokenRates:
    input: Decimal
    cache_write: Decimal
    cache_read: Decimal
    output: Decimal


@dataclass(frozen=True)
class ModelPricing:
    standard: TokenRates
    long_prompt: TokenRates


PRICING_PER_MILLION_TOKENS: dict[str, ModelPricing] = {
    CLAUDE_HAIKU_5_5: ModelPricing(
        standard=TokenRates(
            input=Decimal("0.10"),
            cache_write=Decimal("0.125"),
            cache_read=Decimal("0.01"),
            output=Decimal("0.50"),
        ),
        long_prompt=TokenRates(
            input=Decimal("0.50"),
            cache_write=Decimal("0.625"),
            cache_read=Decimal("0.05"),
            output=Decimal("2.50"),
        ),
    ),
}


def prompt_tokens(usage: ModelUsage) -> int:
    return (
        usage.input_tokens
        + usage.cache_creation_input_tokens
        + usage.cache_read_input_tokens
    )


def rates_for(pricing: ModelPricing, usage: ModelUsage) -> TokenRates:
    if prompt_tokens(usage) > LONG_PROMPT_THRESHOLD_TOKENS:
        return pricing.long_prompt
    return pricing.standard


def tokens_cost(tokens: int, rate_per_million: Decimal) -> Decimal:
    return Decimal(tokens) * rate_per_million / TOKENS_PER_MILLION


def cost_usd(model: str, usage: ModelUsage) -> Decimal | None:
    pricing = PRICING_PER_MILLION_TOKENS.get(model)
    if pricing is None:
        return None
    rates = rates_for(pricing, usage)
    total = (
        tokens_cost(usage.input_tokens, rates.input)
        + tokens_cost(usage.cache_creation_input_tokens, rates.cache_write)
        + tokens_cost(usage.cache_read_input_tokens, rates.cache_read)
        + tokens_cost(usage.output_tokens, rates.output)
    )
    return total.quantize(MICRO_USD, rounding=ROUND_HALF_UP)
