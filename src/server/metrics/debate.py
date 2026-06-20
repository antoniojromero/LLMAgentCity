"""Debate metrics: stance, consensus, persuasion."""

import re
from typing import Dict, List


def estimate_stance(text: str, topic: str = "") -> float:
    """
    Estimate stance on topic (-1 oppose, +1 support, 0 neutral).

    Args:
        text: Message text
        topic: Debate topic (for domain-specific analysis)

    Returns:
        float: -1 to +1 stance score
    """
    text_lower = text.lower()

    # Support indicators
    support_score = 0
    if re.search(r'agree|support|good|positive|benefit|advantage|should|pro', text_lower):
        support_score += 2
    if re.search(r'great|excellent|strong|important|critical', text_lower):
        support_score += 1

    # Oppose indicators
    oppose_score = 0
    if re.search(r'disagree|oppose|bad|negative|problem|issue|disadvantage|against|con', text_lower):
        oppose_score += 2
    if re.search(r'terrible|weak|unimportant|concerning|risky', text_lower):
        oppose_score += 1

    # Neutralize if both present
    if support_score > 0 and oppose_score > 0:
        # Check context - typically mixed messages are slightly negative
        if oppose_score > support_score:
            stance = -(oppose_score - support_score) / 10.0
        else:
            stance = (support_score - oppose_score) / 10.0
    elif support_score > 0:
        stance = support_score / 5.0
    elif oppose_score > 0:
        stance = -oppose_score / 5.0
    else:
        stance = 0.0

    # Clamp to -1, +1 range
    return max(-1.0, min(1.0, stance))


def compute_stance_shift(stance_history: List[float]) -> float:
    """
    Change in stance over recent rounds.

    Args:
        stance_history: List of recent stance values

    Returns:
        float: Change in stance (-1 to +1)
    """
    if not stance_history or len(stance_history) < 2:
        return 0.0

    initial_stance = stance_history[0]
    current_stance = stance_history[-1]

    shift = current_stance - initial_stance

    return max(-1.0, min(1.0, shift))


def compute_consensus_alignment(
    agent_stance: float,
    all_stances: List[float]
) -> float:
    """
    How aligned agent is with group consensus (-1 to +1).

    Args:
        agent_stance: This agent's stance
        all_stances: All agents' stances

    Returns:
        float: 0 (opposite) to 1 (aligned)
    """
    if not all_stances:
        return 0.5

    mean_stance = sum(all_stances) / len(all_stances)

    # Similarity: how close agent is to mean
    distance = abs(agent_stance - mean_stance)
    similarity = 1.0 - (distance / 2.0)  # Max distance is 2 (-1 vs +1)

    return max(0.0, min(1.0, similarity))


def estimate_persuasion_effect(
    pre_stances: Dict[str, float],
    post_stances: Dict[str, float]
) -> Dict[str, float]:
    """
    Estimate which agents persuaded others (post-intervention analysis).

    Args:
        pre_stances: {agent_id: stance} before intervention
        post_stances: {agent_id: stance} after intervention

    Returns:
        dict: {agent_id: persuasion_score}
    """
    persuasion = {}

    for agent_id in pre_stances:
        pre = pre_stances.get(agent_id, 0)
        post = post_stances.get(agent_id, 0)

        # Change magnitude toward consensus
        change = abs(post - pre)

        # Positive change (closer to center) = persuaded
        moved_toward_center = abs(post) < abs(pre)

        persuasion[agent_id] = change if moved_toward_center else 0.0

    return persuasion


def compute_polarization_index(stances: List[float]) -> float:
    """
    Measure of group polarization (0=consensus, 1=maximally polarized).

    Args:
        stances: All agents' stance values

    Returns:
        float: 0-1 polarization index
    """
    if not stances or len(stances) < 2:
        return 0.0

    mean_stance = sum(stances) / len(stances)

    # Compute variance around mean
    variance = sum((s - mean_stance) ** 2 for s in stances) / len(stances)

    # Normalize: max variance is 0.5 (half +1, half -1)
    max_variance = 0.5
    polarization = variance / max_variance if max_variance > 0 else 0

    return min(1.0, polarization)


def compute_consensus_trajectory(stance_history: List[Dict]) -> str:
    """
    Classify consensus trajectory over time.

    Args:
        stance_history: [{round: int, stances: [float]}, ...]

    Returns:
        str: "converging", "diverging", "stable", or "oscillating"
    """
    if not stance_history or len(stance_history) < 2:
        return "unknown"

    # Compute polarization at each round
    polarizations = [
        compute_polarization_index(entry.get("stances", []))
        for entry in stance_history
    ]

    if len(polarizations) < 2:
        return "stable"

    # Check trend
    early_avg = sum(polarizations[:len(polarizations)//2]) / max(1, len(polarizations)//2)
    late_avg = sum(polarizations[len(polarizations)//2:]) / max(1, len(polarizations) - len(polarizations)//2)

    diff = late_avg - early_avg

    if diff < -0.05:
        return "converging"
    elif diff > 0.05:
        return "diverging"
    else:
        return "stable"


def compute_counterargument_density(
    argument_history: List[Dict]
) -> float:
    """
    Fraction of arguments that directly counter previous claims.

    Args:
        argument_history: List of argument objects with claims

    Returns:
        float: 0-1 density
    """
    if not argument_history or len(argument_history) < 2:
        return 0.0

    counter_arguments = 0

    for i, arg in enumerate(argument_history):
        if i == 0:
            continue

        text = arg.get("text", "").lower()

        # Check for counter language
        if re.search(r'but|however|disagree|counter|against|opponent.*claim|false', text):
            counter_arguments += 1

    return min(1.0, counter_arguments / len(argument_history))
