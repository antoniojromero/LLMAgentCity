"""Social network metrics: betweenness, brokerage, participation balance."""

import math
from collections import defaultdict
from typing import Dict, List, Tuple


def compute_betweenness_centrality(
    agent_id: str,
    all_agents: List[Dict],
    interactions: Dict[str, Dict[str, int]]
) -> float:
    """
    Approximate betweenness centrality via interaction graph paths.

    Args:
        agent_id: Agent to measure
        all_agents: List of all agent objects
        interactions: Graph of interactions {agent_id: {other_id: count}}

    Returns:
        float: 0-1 normalized betweenness score
    """
    agent_ids = [a["id"] for a in all_agents]
    if agent_id not in agent_ids or len(agent_ids) < 3:
        return 0.0

    paths_through = 0
    total_paths = 0

    # Simple approximation: count how many pairs are connected through this agent
    for source in agent_ids:
        for target in agent_ids:
            if source != agent_id and target != agent_id and source != target:
                total_paths += 1

                # Check if agent connects source to target
                if (_has_path(source, target, agent_id, interactions) and
                    not _has_direct_path(source, target, agent_id, interactions)):
                    paths_through += 1

    if total_paths == 0:
        return 0.0

    betweenness = paths_through / total_paths
    return min(1.0, betweenness)


def compute_brokerage_score(
    agent_id: str,
    all_agents: List[Dict],
    interactions: Dict[str, Dict[str, int]],
    clusters: List[Dict]
) -> float:
    """
    Fraction of cross-cluster interactions for this agent.

    Args:
        agent_id: Agent to measure
        all_agents: List of all agents
        interactions: Interaction graph
        clusters: List of cluster definitions

    Returns:
        float: 0-1 score, higher = more cross-cluster broker role
    """
    if not interactions.get(agent_id):
        return 0.0

    # Find agent's cluster
    agent_cluster = None
    agent_obj = next((a for a in all_agents if a["id"] == agent_id), None)
    if agent_obj:
        agent_cluster = agent_obj.get("cluster")

    if not agent_cluster:
        return 0.0

    cross_cluster_count = 0
    total_interactions = 0

    for other_id, count in interactions.get(agent_id, {}).items():
        total_interactions += count

        # Check if other_id is in different cluster
        other_obj = next((a for a in all_agents if a["id"] == other_id), None)
        if other_obj and other_obj.get("cluster") != agent_cluster:
            cross_cluster_count += count

    if total_interactions == 0:
        return 0.0

    return min(1.0, cross_cluster_count / total_interactions)


def compute_participation_balance(all_agents: List[Dict]) -> float:
    """
    Gini coefficient of turn distribution (0=equal, 1=dominated).

    Args:
        all_agents: List of all agents with turncount

    Returns:
        float: 0-1 Gini coefficient
    """
    turn_counts = [a.get("turncount", 0) for a in all_agents]

    if not turn_counts or sum(turn_counts) == 0:
        return 0.0

    if len(turn_counts) == 1:
        return 0.0

    # Gini coefficient: 2 * sum(i * x_i) / (n * sum(x)) - (n+1)/n
    sorted_turns = sorted(turn_counts)
    n = len(sorted_turns)

    numerator = sum((i + 1) * turns for i, turns in enumerate(sorted_turns))
    denominator = n * sum(sorted_turns)

    if denominator == 0:
        return 0.0

    gini = 2 * numerator / denominator - (n + 1) / n
    return max(0.0, min(1.0, gini))


def compute_influence_score(agent: Dict) -> float:
    """
    Combined influence from turns, mentions, and connections.

    Args:
        agent: Agent object with metrics

    Returns:
        float: Influence score
    """
    base = 1.0
    base += agent.get("turncount", 0) * 0.1
    base += agent.get("mentions", {}).get("count", 0) * 0.15
    base += len(agent.get("interactions", {})) * 0.2

    # Add sentiment impact
    valence = agent.get("valence", 0)
    base += max(0, valence) * 0.3

    return min(10.0, base)


# Helper functions

def _has_path(
    source: str,
    target: str,
    agent_id: str,
    interactions: Dict[str, Dict[str, int]],
    visited: set = None
) -> bool:
    """Check if there's any path from source to target through agent_id."""
    if visited is None:
        visited = set()

    if source in visited or source == target:
        return source == target

    visited.add(source)

    for neighbor in interactions.get(source, {}):
        if _has_path(neighbor, target, agent_id, interactions, visited):
            return True

    return False


def _has_direct_path(
    source: str,
    target: str,
    exclude_agent: str,
    interactions: Dict[str, Dict[str, int]]
) -> bool:
    """Check if source can reach target without going through exclude_agent."""
    visited = {exclude_agent}
    queue = [source]

    while queue:
        current = queue.pop(0)
        if current == target:
            return True
        if current in visited:
            continue
        visited.add(current)

        for neighbor in interactions.get(current, {}):
            if neighbor not in visited:
                queue.append(neighbor)

    return False
