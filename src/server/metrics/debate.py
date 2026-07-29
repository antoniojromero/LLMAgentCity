"""Debate metrics: stance, consensus alignment (Eq.11), polarization, counterargument, and Coordination building metrics (argument, participation, leadership, alignment, influence)."""

import re
from typing import Dict, List


def estimate_stance(text: str, topic: str = "") -> float:
    """Estimate stance (-1 oppose, +1 support, 0 neutral)."""
    text_lower = text.lower()

    support_score = 0
    if re.search(r'agree|support|good|positive|benefit|advantage|should|pro', text_lower):
        support_score += 2
    if re.search(r'great|excellent|strong|important|critical', text_lower):
        support_score += 1

    oppose_score = 0
    if re.search(r'disagree|oppose|bad|negative|problem|issue|disadvantage|against|con', text_lower):
        oppose_score += 3
    if re.search(r'terrible|weak|unimportant|concerning|risky', text_lower):
        oppose_score += 2

    if support_score > 0 and oppose_score > 0:
        if oppose_score > support_score:
            stance = -(oppose_score - support_score) / (oppose_score + support_score)
        else:
            stance = (support_score - oppose_score) / (oppose_score + support_score)
    elif support_score > 0:
        stance = support_score / 5.0
    elif oppose_score > 0:
        stance = -oppose_score / 5.0
    else:
        stance = 0.0

    return max(-1.0, min(1.0, stance))


def compute_stance_shift(stance_history: List[float]) -> float:
    """Change in stance: current - initial."""
    if not stance_history or len(stance_history) < 2:
        return 0.0
    return max(-1.0, min(1.0, stance_history[-1] - stance_history[0]))


# ──────────────────────────────────────────────────────
# Original consensus alignment, now fixed to use sign-based evaluation per Eq. (11)
# ──────────────────────────────────────────────────────

def compute_consensus_alignment(
    agent_stance: float,
    all_stances: List[float],
    agent_valences: List[dict] = None,
    group_valences: List[dict] = None
) -> float:
    """
    Consensus alignment per Paper Eq. (11):
    Align(v) = 1 - |{t: sign(s_t^v) ≠ sign(s̄_t)}| / |T_v|

    Sign-based: counts turns where agent's valence sign mismatches group mean.
    """
    if agent_valences and group_valences and len(agent_valences) > 0:
        mismatches = 0
        for tv in agent_valences:
            v_sign = 1 if tv.get("valence", 0) > 0 else -1 if tv.get("valence", 0) < 0 else 0
            if v_sign == 0:
                continue
            t = tv.get("turn")
            g = next((gv for gv in group_valences if gv.get("turn") == t), None)
            if g:
                g_sign = 1 if g.get("mean_valence", 0) > 0 else -1 if g.get("mean_valence", 0) < 0 else 0
                if g_sign != 0 and v_sign != g_sign:
                    mismatches += 1
        if len(agent_valences) == 0:
            return 0.5
        return round(1.0 - mismatches / len(agent_valences), 4)

    if not all_stances:
        return 0.5
    return round(max(0.0, min(1.0, 1.0 - abs(agent_stance - sum(all_stances) / len(all_stances)) / 2.0)), 4)


def compute_polarization_index(stances: List[float]) -> float:
    """Group polarization (0=consensus, 1=maximally polarized)."""
    if not stances or len(stances) < 2:
        return 0.0
    mean_stance = sum(stances) / len(stances)
    variance = sum((s - mean_stance) ** 2 for s in stances) / len(stances)
    max_variance = 0.5
    return min(1.0, variance / max_variance) if max_variance > 0 else 0


def compute_consensus_trajectory(stance_history: List[Dict]) -> str:
    """Classify consensus trajectory: converging, diverging, stable."""
    if not stance_history or len(stance_history) < 2:
        return "unknown"
    polarizations = [compute_polarization_index(entry.get("stances", []))
                     for entry in stance_history]
    if len(polarizations) < 2:
        return "stable"
    early_avg = sum(polarizations[:len(polarizations)//2]) / max(1, len(polarizations)//2)
    late_avg = sum(polarizations[len(polarizations)//2:]) / max(1, len(polarizations) - len(polarizations)//2)
    diff = late_avg - early_avg
    if diff < -0.05:
        return "converging"
    elif diff > 0.05:
        return "diverging"
    return "stable"


def compute_counterargument_density(argument_history: List[Dict]) -> float:
    """Fraction of arguments that counter previous claims."""
    if not argument_history or len(argument_history) < 2:
        return 0.0
    counter_args = sum(1 for arg in argument_history
                       if re.search(r'but|however|disagree|counter|against|false', arg.get("text", "").lower()))
    return round(min(1.0, counter_args / len(argument_history)), 4)


def estimate_persuasion_effect(pre_stances: Dict[str, float],
                               post_stances: Dict[str, float]) -> Dict[str, float]:
    """Estimate which agents moved toward consensus post-intervention."""
    return {aid: abs(post - pre) for aid, pre in pre_stances.items()
            if abs(post_stances.get(aid, 0)) < abs(pre)}


# ──────────────────────────────────────────────────────
# Coordination Building 1: Argument (height, width, depth)
# ──────────────────────────────────────────────────────

def compute_argument_strength(word_count: int, turn_count: int, reference_length: float = 50.0) -> float:
    """
    avg words per turn normalized by reference length (Paper Eq. 9).
    """
    if turn_count <= 0 or word_count <= 0:
        return 0.0
    avg_words = word_count / turn_count
    return round(min(avg_words / max(reference_length, 1), 1.0), 4)


def compute_planning_load(agent: Dict) -> float:
    """
    Fraction of turns containing task-coordination signals (file references, task labels).
    """
    messages = agent.get("message_history", [])
    if not messages:
        return 0.0

    planning_patterns = [
        r'\b(file|document|report|code|artifact|module|src|README|TODO|FIXME)\b',
        r'\b(fix|implement|build|deploy|test|merge|review|refactor|api|endpoint)\b',
        r'\b(\.py|\.js|\.ts|\.go|\.rs|\.java|\.css|\.html|\.json|\.yaml|\.yml)\b',
        r'\b(step|checklist|milestone|deadline|sprint|task|assign|priority)\b',
    ]

    planning_turns = 0
    for msg in messages:
        text = str(msg).lower()
        if any(re.search(p, text) for p in planning_patterns):
            planning_turns += 1

    return round(min(planning_turns / len(messages), 1.0), 4)


def compute_review_depth(argument_score: float, turn_count: int) -> float:
    """
    Accumulated critique score — number of prior turns referenced per review turn.
    Normalized by max expected argents (10).
    """
    if turn_count <= 0:
        return 0.0
    return round(min(argument_score / 10.0, 1.0), 4)


# ──────────────────────────────────────────────────────
# Coordination Building 2: Participation (height, width, depth)
# ──────────────────────────────────────────────────────

def compute_turn_taking_equity(agent_turn_count: int, total_turns: int, total_agents: int) -> float:
    """
    1 - |(agent_turns / total_turns) - (1/n)|  (Paper Eq. 12).
    """
    if total_turns <= 0 or total_agents <= 0:
        return 0.0
    share = agent_turn_count / total_turns
    equal_share = 1.0 / total_agents
    return round(max(0.0, 1.0 - abs(share - equal_share)), 4)


def compute_stance_intensity(detected_emotions: Dict) -> float:
    """
    Mean intensity of detected emotions, normalised to 0–1.
    """
    if not detected_emotions:
        return 0.0
    intensities = []
    for entry in detected_emotions.values():
        if isinstance(entry, dict):
            intensities.append(entry.get("total_intensity", entry.get("intensity", 0.0)))
        elif isinstance(entry, (int, float)):
            intensities.append(float(entry))
    if not intensities:
        return 0.0
    return round(min(sum(intensities) / len(intensities), 1.0), 4)


def compute_initiative_ratio(valence_history: List[float]) -> float:
    """
    Frequency of significant sentiment shifts (>0.1) per turn — proxies topic-change initiative.
    """
    if not valence_history or len(valence_history) < 2:
        return 0.0
    shifts = 0
    for i in range(1, len(valence_history)):
        if abs(valence_history[i] - valence_history[i - 1]) > 0.1:
            shifts += 1
    return round(shifts / max(len(valence_history) - 1, 1), 4)


# ──────────────────────────────────────────────────────
# Coordination Building 3: Leadership (height, width, depth)
# ──────────────────────────────────────────────────────

def compute_delegation_load(planning_load: float, text: str) -> float:
    """
    Planning signals + delegation language markers.
    """
    delegation_markers = [
        "assign", "delegate", "responsible", "task",
        "we should", "let's", "our", "we need",
        "you handle", "take care of", "your part", "on you",
    ]
    text_lower = text.lower()
    words = text_lower.split()
    delegation_count = sum(1 for marker in delegation_markers if marker in text_lower)
    delegation_scale = (delegation_count / max(len(words), 1)) * 10.0
    return round(min(planning_load * 0.6 + delegation_scale * 0.4, 1.0), 4)


def compute_convergence_contribution(polarity_mismatch: float) -> float:
    """
    Complement of polarity mismatch: 1 - polarity_mismatch.
    """
    return round(max(0.0, min(1.0, 1.0 - polarity_mismatch)), 4)


# ──────────────────────────────────────────────────────
# Coordination Building 4: Alignment (height, width, depth)
# ──────────────────────────────────────────────────────

def compute_group_alignment(polarity_mismatch: float) -> float:
    """
    1 - polarity_mismatch (identical logic to convergence_contribution).
    """
    return round(max(0.0, min(1.0, 1.0 - polarity_mismatch)), 4)


def compute_xref_load(agent_history: List[Dict]) -> float:
    """
    Frequency of citations / external references per turn.
    """
    if not agent_history:
        return 0.0

    citation_patterns = [
        r'https?://', r'@\w+', r'#\d+', r'PR\s*#?\d+',
        r'mentioned', r'cited', r'according to', r'\bsays\b',
        r'issue\s*#?\d+', r'commit\s*[a-f0-9]+',
        r'line\s+\d+', r'reference:', r'see\s+', r'cf\.\s',
        r'\[.*\]\(.*\)', r'File:', r'Path:',
    ]

    xref_turns = 0
    for entry in agent_history:
        text = str(entry.get("text", entry) if isinstance(entry, dict) else entry).lower()
        if any(re.search(p, text) for p in citation_patterns):
            xref_turns += 1

    return round(min(xref_turns / len(agent_history), 1.0), 4) if agent_history else 0.0


# ──────────────────────────────────────────────────────
# Coordination Building 5: Influence (height, width, depth)
# ──────────────────────────────────────────────────────

def compute_network_reach(interactions: Dict[str, int]) -> int:
    """Total interactions = sum of interaction values."""
    if not interactions:
        return 0
    return sum(interactions.values())


def compute_partner_span(interactions: Dict[str, int]) -> int:
    """Number of distinct partners."""
    if not interactions:
        return 0
    return len(interactions)


def compute_overall_influence(
    network_reach: float,
    partner_span: int,
    total_agents: int,
    turn_count: int
) -> float:
    """Generic influence score combining reach, span, and throughput normalised by total agents and turns."""
    if total_agents <= 0 or turn_count <= 0:
        return 0.0
    partner_ratio = partner_span / max(total_agents - 1, 1)
    density = min(network_reach / max(turn_count, 1), 1.0)
    return round(min((partner_ratio + density) / 2.0, 1.0), 4)