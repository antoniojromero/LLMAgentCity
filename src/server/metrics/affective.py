"""Affective metrics: emotion diversity, arousal variance, contagion, etc."""

import math
from collections import Counter
from typing import Dict, List


def compute_emotion_diversity(detected_emotions: Dict[str, int]) -> float:
    """
    Shannon entropy of emotion distribution (normalized).

    Args:
        detected_emotions: {emotion_type: count}

    Returns:
        float: 0 (single emotion) to 3.1 (uniform 22 emotions)
    """
    if not detected_emotions or sum(detected_emotions.values()) == 0:
        return 0.0

    total = sum(detected_emotions.values())
    probabilities = [count / total for count in detected_emotions.values()]

    entropy = -sum(p * math.log2(p) for p in probabilities if p > 0)

    # Normalize to 0-1 range (max entropy for 22 emotions ≈ 4.75)
    max_entropy = math.log2(22)  # ≈ 4.75
    normalized = entropy / max_entropy if max_entropy > 0 else 0

    return min(1.0, normalized)


def compute_dominant_emotion(detected_emotions: Dict[str, int]) -> str:
    """
    Emotion type with highest count.

    Args:
        detected_emotions: {emotion_type: count}

    Returns:
        str: Emotion name or empty string if none detected
    """
    if not detected_emotions:
        return ""

    return max(detected_emotions, key=detected_emotions.get)


def compute_arousal_variance(arousal_history: List[float]) -> float:
    """
    Variance of arousal over recent message history.

    Args:
        arousal_history: List of recent arousal values

    Returns:
        float: Normalized variance (0-1)
    """
    if not arousal_history or len(arousal_history) < 2:
        return 0.0

    mean_arousal = sum(arousal_history) / len(arousal_history)
    variance = sum((x - mean_arousal) ** 2 for x in arousal_history) / len(arousal_history)

    # Normalize: max variance when -1 to +1 = 0.667
    normalized = variance / 0.667 if variance > 0 else 0

    return min(1.0, normalized)


def compute_emotion_contagion(
    agent_id: str,
    all_agents: List[Dict],
    message_history: List[Dict],
    interactions: Dict[str, Dict[str, int]]
) -> float:
    """
    Proxy for emotion contagion: emotional similarity to interacting agents.

    Args:
        agent_id: Agent to measure
        all_agents: List of all agents
        message_history: Chronological messages
        interactions: Interaction graph

    Returns:
        float: -1 (opposite emotions) to +1 (aligned emotions)
    """
    agent = next((a for a in all_agents if a["id"] == agent_id), None)
    if not agent:
        return 0.0

    agent_valence = agent.get("valence", 0)
    agent_arousal = agent.get("arousal", 0)

    # Get agents this agent interacts with
    interacting_agents = interactions.get(agent_id, {})
    if not interacting_agents:
        return 0.0

    # Compute average emotional state of interacting partners
    partner_valences = []
    partner_arousals = []

    for partner_id in interacting_agents:
        partner = next((a for a in all_agents if a["id"] == partner_id), None)
        if partner:
            partner_valences.append(partner.get("valence", 0))
            partner_arousals.append(partner.get("arousal", 0))

    if not partner_valences:
        return 0.0

    avg_partner_valence = sum(partner_valences) / len(partner_valences)
    avg_partner_arousal = sum(partner_arousals) / len(partner_arousals)

    # Compute similarity as 1 - normalized distance
    valence_diff = abs(agent_valence - avg_partner_valence)
    arousal_diff = abs(agent_arousal - avg_partner_arousal)

    distance = (valence_diff + arousal_diff) / 4  # Max distance = 4
    similarity = 1 - distance

    return max(-1.0, min(1.0, similarity))


def compute_dominant_emotion_intensity(
    detected_emotions: Dict[str, int]
) -> float:
    """
    Intensity (normalized count) of dominant emotion.

    Args:
        detected_emotions: {emotion_type: count}

    Returns:
        float: 0-1 normalized intensity
    """
    if not detected_emotions:
        return 0.0

    max_count = max(detected_emotions.values())
    total = sum(detected_emotions.values())

    intensity = max_count / total if total > 0 else 0

    return min(1.0, intensity)


def compute_emotional_stability(
    valence_history: List[float],
    arousal_history: List[float]
) -> float:
    """
    Stability index: inverse of combined variance.

    Args:
        valence_history: Recent valence values
        arousal_history: Recent arousal values

    Returns:
        float: 0 (unstable) to 1 (stable)
    """
    if not valence_history or not arousal_history:
        return 0.5  # Unknown = neutral

    if len(valence_history) < 2:
        return 1.0  # Single value = stable

    # Compute variances
    valence_var = sum((x - sum(valence_history)/len(valence_history))**2
                      for x in valence_history) / len(valence_history)
    arousal_var = sum((x - sum(arousal_history)/len(arousal_history))**2
                      for x in arousal_history) / len(arousal_history)

    combined_variance = (valence_var + arousal_var) / 2

    # Inverse: higher variance = lower stability
    stability = 1.0 / (1.0 + combined_variance)

    return min(1.0, max(0.0, stability))
