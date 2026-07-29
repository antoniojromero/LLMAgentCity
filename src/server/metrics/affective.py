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
        float: 0 (single emotion) to 1 (uniform across 22 emotions)
    """
    if not detected_emotions or sum(detected_emotions.values()) == 0:
        return 0.0

    total = sum(detected_emotions.values())
    probabilities = [count / total for count in detected_emotions.values()]

    entropy = -sum(p * math.log2(p) for p in probabilities if p > 0)

    return entropy


def compute_dominant_emotion(detected_emotions: Dict[str, int]) -> str:
    """
    Emotion type with highest count.

    Args:
        detected_emotions: {emotion_type: count}

    Returns:
        str: Emotion name or empty string if none detected
    """
    if not detected_emotions:
        return None

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

    interacting_agents = interactions.get(agent_id, {})
    if not interacting_agents:
        return 0.0

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

    valence_diff = abs(agent_valence - avg_partner_valence)
    arousal_diff = abs(agent_arousal - avg_partner_arousal)

    distance = (valence_diff + arousal_diff) / 4
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
        return 0.5

    if len(valence_history) < 2:
        return 1.0

    valence_var = sum((x - sum(valence_history)/len(valence_history))**2
                      for x in valence_history) / len(valence_history)
    arousal_var = sum((x - sum(arousal_history)/len(arousal_history))**2
                      for x in arousal_history) / len(arousal_history)

    combined_variance = (valence_var + arousal_var) / 2

    stability = 1.0 / (1.0 + combined_variance)

    return min(1.0, max(0.0, stability))


def compute_valence_volatility(valence_history: List[float]) -> float:
    """
    Standard deviation of valence over recent window.

    Args:
        valence_history: List of recent valence values

    Returns:
        float: 0 (constant valence) to ~1 (highly volatile)
    """
    if not valence_history or len(valence_history) < 2:
        return 0.0

    n = len(valence_history)
    mean_v = sum(valence_history) / n
    variance = sum((v - mean_v) ** 2 for v in valence_history) / n

    return variance ** 0.5


def compute_sentiment_drift(valence_history: List[float]) -> float:
    """
    Slope of linear regression of valence over time.

    Args:
        valence_history: List of recent valence values (chronological)

    Returns:
        float: Slope (positive = improving mood, negative = declining mood)
    """
    if not valence_history or len(valence_history) < 2:
        return 0.0

    n = len(valence_history)
    x = list(range(n))
    mean_x = sum(x) / n
    mean_v = sum(valence_history) / n

    numerator = sum((x[i] - mean_x) * (valence_history[i] - mean_v) for i in range(n))
    denominator = sum((xi - mean_x) ** 2 for xi in x)

    if abs(denominator) < 1e-10:
        return 0.0

    return numerator / denominator


def compute_polarity_alignment(
    agent_valence_history: List[float],
    group_valence_history: List[float]
) -> float:
    """
    Fraction of turns where agent polarity (sign of valence) matches group polarity.

    Args:
        agent_valence_history: Agent's valence values per turn
        group_valence_history: Group average valence values per turn

    Returns:
        float: 0 (always opposite) to 1 (always aligned)
    """
    if not agent_valence_history or not group_valence_history:
        return 0.5

    n = min(len(agent_valence_history), len(group_valence_history))
    if n == 0:
        return 0.5

    mismatches = sum(
        1 for i in range(n)
        if (agent_valence_history[i] > 0) != (group_valence_history[i] > 0)
    )

    return 1.0 - (mismatches / n)


def compute_affective_influence(sentiment_drift: float, betweennessproxy: float) -> float:
    """
    Affective influence as product of sentiment drift magnitude and betweenness.

    Args:
        sentiment_drift: Slope of valence over time
        betweennessproxy: Agent's betweenness/proxy centrality

    Returns:
        float: Non-negative influence score
    """
    return abs(sentiment_drift) * abs(betweennessproxy)


def compute_toxicity_score(agent_valence: float, agent_arousal: float, text: str) -> float:
    """
    Weighted combination of negative valence, high arousal, and toxic language markers.

    Args:
        agent_valence: Current valence (-1 to +1)
        agent_arousal: Current arousal (0 to 1)
        text: Latest message text

    Returns:
        float: 0 (benign) to 1 (highly toxic)
    """
    negative_component = max(0.0, -agent_valence)

    toxic_words = [
        "bad", "hate", "terrible", "awful", "stupid",
        "idiotic", "wrong", "fail", "kill", "destroy",
        "worthless", "pathetic", "useless", "garbage"
    ]
    words = text.lower().split()
    word_count = max(len(words), 1)
    toxic_count = sum(1 for word in words if word in toxic_words)
    toxic_ratio = toxic_count / word_count

    score = (
        negative_component * 0.5
        + agent_arousal * 0.3
        + toxic_ratio * 10 * 0.2
    )

    return min(1.0, max(0.0, score))


def compute_emotional_inertia(valence_history: List[float]) -> float:
    """
    Autocorrelation of valence at lag 1 (Pearson-like).

    Args:
        valence_history: Chronological valence values

    Returns:
        float: -1 (perfect oscillation) to +1 (perfect persistence)
    """
    if not valence_history or len(valence_history) < 3:
        return 0.0

    v_t = valence_history[:-1]
    v_t1 = valence_history[1:]
    n = len(v_t)

    mean_t = sum(v_t) / n
    mean_t1 = sum(v_t1) / n

    numerator = sum((v_t[i] - mean_t) * (v_t1[i] - mean_t1) for i in range(n))
    denom_t = sum((v - mean_t) ** 2 for v in v_t)
    denom_t1 = sum((v - mean_t1) ** 2 for v in v_t1)
    denominator = (denom_t * denom_t1) ** 0.5

    if denominator < 1e-10:
        return 0.0

    return min(1.0, max(-1.0, numerator / denominator))


def compute_emotion_count(detected_emotions: Dict[str, Dict]) -> int:
    """
    Total number of emotion detections across all types.

    Args:
        detected_emotions: {emotion_type: {count: int, ...}}

    Returns:
        int: Sum of all individual emotion counts
    """
    if not detected_emotions:
        return 0

    return sum(
        emo_data.get("count", 0)
        if isinstance(emo_data, dict)
        else int(emo_data)
        for emo_data in detected_emotions.values()
    )


def compute_emotion_variety(detected_emotions: Dict[str, Dict]) -> int:
    """
    Number of distinct emotion types the agent has experienced.

    Args:
        detected_emotions: {emotion_type: {count: int, ...}}

    Returns:
        int: Count of distinct emotion types
    """
    if not detected_emotions:
        return 0

    return len(detected_emotions)