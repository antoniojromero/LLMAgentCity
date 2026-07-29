"""Operational metrics: cost (alpha*P + beta*C), latency, token efficiency (type-token)."""

import math
import re
from typing import Dict, List


def compute_cost_per_turn(agent: Dict, alpha: float = 0.0, beta: float = 0.0) -> float:
    """
    Cost per turn as linear pricing model.
    Paper Eq. (5): kappa_i = alpha * P_i + beta * C_i

    Args:
        agent: Agent with prompttokens and completiontokens
        alpha: Cost per prompt token (USD)
        beta: Cost per completion token (USD)

    Returns:
        float: USD cost per turn
    """
    if alpha == 0.0 and beta == 0.0:
        total_cost = agent.get("total_cost_usd", 0.0)
        turn_count = agent.get("turncount", agent.get("turn_count", 1))
        if turn_count == 0:
            return 0.0
        return round(total_cost / turn_count, 6)

    P = agent.get("prompttokens", agent.get("prompt_tokens", 0))
    C = agent.get("completiontokens", agent.get("completion_tokens", 0))
    turn_count = agent.get("turncount", agent.get("turn_count", 1))
    if turn_count == 0:
        return 0.0
    return round((alpha * P + beta * C) / turn_count, 6)


def compute_latency_variance(latency_samples: List[float]) -> float:
    """Variance of latency measurements (normalized 0-1)."""
    if not latency_samples or len(latency_samples) < 2:
        return 0.0

    mean_latency = sum(latency_samples) / len(latency_samples)
    variance = sum((x - mean_latency) ** 2 for x in latency_samples) / len(latency_samples)

    max_variance = (mean_latency * 2) ** 2 if mean_latency > 0 else 1
    normalized = variance / max_variance
    return min(1.0, normalized)


def compute_prompt_completion_ratio(agent: Dict) -> float:
    """Ratio of prompt tokens to completion tokens."""
    prompt_tokens = agent.get("prompttokens", 0)
    completion_tokens = agent.get("completiontokens", 1)
    if completion_tokens == 0:
        return 1.0
    ratio = prompt_tokens / completion_tokens
    return max(0.1, min(10.0, ratio))


def compute_token_efficiency(agent: Dict) -> float:
    """
    Type-Token Ratio of agent's output.
    Paper Eq. (6): Eff_i = |unique_words(C_i)| / |C_i|
    """
    messages = agent.get("sentencetexts", []) or agent.get("messagehistory", [])
    if not messages:
        return 0.0

    all_words = []
    for msg in messages:
        text = msg.get("text", "") if isinstance(msg, dict) else str(msg)
        all_words.extend(re.findall(r'\b\w+\b', text.lower()))

    if not all_words:
        return 0.0

    return round(len(set(all_words)) / len(all_words), 4)


def compute_token_efficiency_ratio(agent: Dict) -> float:
    """
    Tokens generated per second (throughput efficiency).
    Paper: T_i = C_i / t_i
    """
    total_tokens = agent.get("totaltokens", 0)
    turn_count = agent.get("turncount", 1)
    avg_latency_ms = agent.get("avglatencyms", 1000)

    if avg_latency_ms == 0 or turn_count == 0:
        return 0.0

    tokens_per_ms = total_tokens / (avg_latency_ms * turn_count)
    tokens_per_sec = tokens_per_ms * 1000

    return max(0.0, tokens_per_sec)


def compute_latency_percentile(
    latency_samples: List[float],
    percentile: int = 95
) -> float:
    """P95 latency."""
    if not latency_samples:
        return 0.0
    sorted_samples = sorted(latency_samples)
    index = int((percentile / 100) * len(sorted_samples))
    index = min(index, len(sorted_samples) - 1)
    return sorted_samples[index]


def compute_average_latency(agent: Dict) -> float:
    """Average latency."""
    return agent.get("avglatencyms", 0.0)


def compute_throughput(agent: Dict) -> float:
    """Throughput: total_tokens / (avg_latency_ms * turn_count / 1000)."""
    total_tokens = agent.get("totaltokens", 0)
    turn_count = agent.get("turncount", 1)
    avg_latency_ms = agent.get("avglatencyms", 1000)

    if turn_count == 0 or avg_latency_ms == 0:
        return 0.0

    return total_tokens / (avg_latency_ms * turn_count / 1000)


def compute_latency_stability(latency_variance: float) -> float:
    """Stability: 1 - normalized latency variance."""
    return 1.0 - min(1.0, latency_variance)


def compute_context_utilization(agent: Dict, max_tensor: int = 8000) -> float:
    """Context utilization: prompt_tokens / model_max_context."""
    prompt_tokens = agent.get("prompttokens", 0)
    if max_tensor <= 0:
        return 0.0
    return min(1.0, prompt_tokens / max_tensor)


def compute_cost_variance(message_history: List[Dict], alpha: float = 0.0, beta: float = 0.0) -> float:
    """Variance of cost per turn across message history."""
    if not message_history or len(message_history) < 2:
        return 0.0

    costs = []
    for msg in message_history:
        P = msg.get("prompttokens", 0)
        C = msg.get("completiontokens", 0)
        turn_count = msg.get("turncount", 1)
        if turn_count > 0:
            cost = (alpha * P + beta * C) / turn_count
            costs.append(cost)
        else:
            costs.append(0.0)

    if len(costs) < 2:
        return 0.0

    mean_cost = sum(costs) / len(costs)
    variance = sum((c - mean_cost) ** 2 for c in costs) / len(costs)

    max_variance = (mean_cost * 2) ** 2 if mean_cost > 0 else 1
    normalized = variance / max_variance
    return min(1.0, normalized)


def compute_retry_rate(latency_variance: float) -> float:
    """Proxy for retry rate: normalized latency variance."""
    return min(1.0, latency_variance)


def compute_cost_stability(cost_variance: float) -> float:
    """Cost stability: 1 - normalized cost variance."""
    return 1.0 - min(1.0, cost_variance)


def compute_generation_rate(throughput: float, reference: float = 5.0) -> float:
    """Generation rate: tokens per second capped at reference."""
    if reference <= 0:
        return 0.0
    return min(1.0, throughput / reference)


def compute_response_speed(avg_latency_ms: float, max_latency: float = 5000.0) -> float:
    """Response speed: log-normalized latency inverted (faster=higher)."""
    if avg_latency_ms <= 0 or max_latency <= 0:
        return 1.0
    log_norm = math.log(1 + avg_latency_ms) / math.log(1 + max_latency)
    return 1.0 - min(1.0, log_norm)


def compute_cost_efficiency(cost_per_turn: float, max_cost: float = 0.1) -> float:
    """Cost efficiency: log-normalized cost inverted (cheaper=higher)."""
    if cost_per_turn <= 0 or max_cost <= 0:
        return 1.0
    log_norm = math.log(1 + cost_per_turn) / math.log(1 + max_cost)
    return 1.0 - min(1.0, log_norm)