"""Conversation metrics: speech acts, lexical diversity, etc."""

import re
from collections import Counter
from typing import Dict, List


def classify_speech_acts(text: str) -> Dict[str, int]:
    """
    Heuristic classification of speech acts in text.

    Args:
        text: Agent message text

    Returns:
        dict: {act_type: count}
    """
    text_lower = text.lower()

    acts = {
        "question": 0,
        "proposal": 0,
        "agreement": 0,
        "disagreement": 0,
        "challenge": 0,
        "summary": 0,
    }

    # Question patterns
    if re.search(r'\?|what|why|how|can|could|should|would', text_lower):
        acts["question"] += 1

    # Proposal patterns
    if re.search(r'should|let\'s|propose|suggest|recommend|we could', text_lower):
        acts["proposal"] += 1

    # Agreement patterns
    if re.search(r'agree|exactly|good point|yes|correct|right|indeed|absolutely', text_lower):
        acts["agreement"] += 1

    # Disagreement patterns
    if re.search(r'but|however|disagree|not|no|wrong|incorrect|i disagree', text_lower):
        acts["disagreement"] += 1

    # Challenge patterns
    if re.search(r'challenge|question|doubt|skeptic|disagree|but.*assumes', text_lower):
        acts["challenge"] += 1

    # Summary patterns
    if re.search(r'summary|overall|so far|in summary|to summarize|summarize', text_lower):
        acts["summary"] += 1

    return acts


def compute_lexical_diversity(message_history: List[str]) -> float:
    """
    Type-Token Ratio of agent's messages.

    Args:
        message_history: List of all agent messages

    Returns:
        float: 0.1 (repetitive) to 1.0 (unique vocabulary)
    """
    if not message_history:
        return 0.0

    # Tokenize all messages
    all_text = " ".join(message_history).lower()
    tokens = re.findall(r'\b\w+\b', all_text)

    if not tokens:
        return 0.0

    unique_tokens = len(set(tokens))
    total_tokens = len(tokens)

    if total_tokens == 0:
        return 0.0

    type_token_ratio = unique_tokens / total_tokens

    # Cap at reasonable range
    return max(0.1, min(1.0, type_token_ratio))


def compute_referencing_density(
    agent_id: str,
    message_history: List[Dict]
) -> float:
    """
    Density of mentions/references to other agents.

    Args:
        agent_id: Agent to measure
        message_history: List of messages with author and mentions

    Returns:
        float: 0-1 referencing density
    """
    agent_messages = [m for m in message_history if m.get("author") == agent_id]

    if not agent_messages:
        return 0.0

    messages_with_refs = sum(
        1 for m in agent_messages
        if m.get("mentions") and len(m.get("mentions", [])) > 0
    )

    density = messages_with_refs / len(agent_messages) if agent_messages else 0

    return min(1.0, density)


def compute_reply_depth_proxy(
    agent_id: str,
    message_history: List[Dict]
) -> float:
    """
    Proxy for threading depth (how many levels of responses).

    Args:
        agent_id: Agent to measure
        message_history: Chronological messages with indices

    Returns:
        float: Average nesting depth (normalized)
    """
    # Simplified proxy: measure gaps between agent's messages
    agent_indices = [
        i for i, m in enumerate(message_history)
        if m.get("author") == agent_id
    ]

    if not agent_indices or len(agent_indices) < 2:
        return 0.0

    # Compute gaps
    gaps = [agent_indices[i+1] - agent_indices[i] for i in range(len(agent_indices)-1)]

    avg_gap = sum(gaps) / len(gaps)

    # Normalize: gaps > 5 = complex threading
    depth = min(1.0, avg_gap / 10.0)

    return depth


def compute_speech_act_distribution(all_messages: List[Dict]) -> Dict[str, float]:
    """
    Distribution of speech acts across all messages.

    Args:
        all_messages: List of all message objects with text

    Returns:
        dict: {act_type: fraction}
    """
    if not all_messages:
        return {
            "question": 0,
            "proposal": 0,
            "agreement": 0,
            "disagreement": 0,
            "challenge": 0,
            "summary": 0,
        }

    total_acts = {
        "question": 0,
        "proposal": 0,
        "agreement": 0,
        "disagreement": 0,
        "challenge": 0,
        "summary": 0,
    }

    for msg in all_messages:
        acts = classify_speech_acts(msg.get("text", ""))
        for act_type, count in acts.items():
            total_acts[act_type] += count

    total_count = sum(total_acts.values())

    if total_count == 0:
        return total_acts

    distribution = {act: count / total_count for act, count in total_acts.items()}

    return distribution


def compute_message_length_variance(message_history: List[str]) -> float:
    """
    Variance in message lengths (normalized).

    Args:
        message_history: List of messages

    Returns:
        float: 0-1 normalized variance
    """
    if not message_history or len(message_history) < 2:
        return 0.0

    lengths = [len(m.split()) for m in message_history]
    mean_length = sum(lengths) / len(lengths)

    variance = sum((x - mean_length) ** 2 for x in lengths) / len(lengths)

    # Normalize
    max_variance = mean_length ** 2 if mean_length > 0 else 1
    normalized = variance / max_variance

    return min(1.0, normalized)
