"""Operational metrics: cost, latency, token efficiency."""

import math
from typing import Dict, List


def compute_cost_per_turn(agent: Dict) -> float:
    """
    Average cost per speaking turn.

    Args:
        agent: Agent object with totalcostusd and turncount

    Returns:
        float: USD cost per turn
    """
    total_cost = agent.get("totalcostusd", 0)
    turn_count = agent.get("turncount", 1)

    if turn_count == 0:
        return 0.0

    cost_per_turn = total_cost / turn_count

    return max(0.0, cost_per_turn)


def compute_latency_variance(latency_samples: List[float]) -> float:
    """
    Variance of latency measurements (normalized).

    Args:
        latency_samples: Recent latency values in milliseconds

    Returns:
        float: 0-1 normalized variance
    """
    if not latency_samples or len(latency_samples) < 2:
        return 0.0

    mean_latency = sum(latency_samples) / len(latency_samples)
    variance = sum((x - mean_latency) ** 2 for x in latency_samples) / len(latency_samples)

    # Normalize: assume max variance ~= (mean * 2)^2
    max_variance = (mean_latency * 2) ** 2 if mean_latency > 0 else 1
    normalized = variance / max_variance

    return min(1.0, normalized)


def compute_prompt_completion_ratio(agent: Dict) -> float:
    """
    Ratio of prompt tokens to completion tokens.

    Args:
        agent: Agent with prompttokens and completiontokens

    Returns:
        float: Ratio (1.0 = equal, >1.0 = more prompt, <1.0 = more completion)
    """
    prompt_tokens = agent.get("prompttokens", 0)
    completion_tokens = agent.get("completiontokens", 1)

    if completion_tokens == 0:
        return 0.0

    ratio = prompt_tokens / completion_tokens

    # Cap at reasonable range
    return max(0.1, min(10.0, ratio))


def compute_token_efficiency(agent: Dict) -> float:
    """
    Tokens per turn normalized by output quality proxy.

    Args:
        agent: Agent with totaltokens, turncount, valence (quality proxy)

    Returns:
        float: 0-1 efficiency score (higher = more efficient)
    """
    total_tokens = agent.get("totaltokens", 1)
    turn_count = agent.get("turncount", 1)
    valence = agent.get("valence", 0)

    tokens_per_turn = total_tokens / max(1, turn_count)

    # Efficiency = (max_tokens_per_turn - actual) / max_tokens_per_turn
    # Assume 5000 tokens/turn as high threshold
    max_tokens = 5000
    efficiency = 1.0 - (tokens_per_turn / max_tokens)

    # Quality adjustment: positive valence suggests better quality
    quality_bonus = max(0, valence) * 0.2

    efficiency = efficiency + quality_bonus

    return max(0.0, min(1.0, efficiency))


def compute_latency_percentile(
    latency_samples: List[float],
    percentile: int = 95
) -> float:
    """
    Percentile latency (e.g., 95th percentile).

    Args:
        latency_samples: List of latency values in ms
        percentile: Percentile to compute (default 95)

    Returns:
        float: Latency at percentile in milliseconds
    """
    if not latency_samples:
        return 0.0

    sorted_samples = sorted(latency_samples)
    index = int((percentile / 100) * len(sorted_samples))
    index = min(index, len(sorted_samples) - 1)

    return sorted_samples[index]


def compute_average_latency(agent: Dict) -> float:
    """
    Average latency from agent metrics.

    Args:
        agent: Agent with avglatencyms

    Returns:
        float: Average latency in milliseconds
    """
    return agent.get("avglatencyms", 0.0)


def compute_token_efficiency_ratio(agent: Dict) -> float:
    """
    Tokens generated per millisecond (throughput efficiency).

    Args:
        agent: Agent with totaltokens and avglatencyms

    Returns:
        float: Tokens per second (higher = better throughput)
    """
    total_tokens = agent.get("totaltokens", 0)
    turn_count = agent.get("turncount", 1)
    avg_latency_ms = agent.get("avglatencyms", 1000)

    if avg_latency_ms == 0 or turn_count == 0:
        return 0.0

    tokens_per_ms = total_tokens / (avg_latency_ms * turn_count)
    tokens_per_sec = tokens_per_ms * 1000

    return max(0.0, tokens_per_sec)
