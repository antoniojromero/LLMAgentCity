"""Social network metrics: betweenness, closeness, brokerage, reciprocity, interaction diversity."""

import math
import networkx as nx
from collections import defaultdict
from typing import Dict, List


def compute_betweenness_centrality(
    agent_id: str,
    all_agents: List[Dict],
    interactions: Dict[str, Dict[str, int]]
) -> float:
    """
    Betweenness centrality using Brandes's algorithm via NetworkX.
    Paper Eq. (1): B(v) = sum_{s≠v≠t} sigma_st(v) / sigma_st
    """
    G = _build_graph(all_agents, interactions)
    if agent_id not in G:
        return 0.0
    if len(G) < 3:
        return 0.0
    scores = nx.betweenness_centrality(G, normalized=True, weight="weight")
    return round(scores.get(agent_id, 0.0), 4)


def compute_closeness_centrality(
    agent_id: str,
    all_agents: List[Dict],
    interactions: Dict[str, Dict[str, int]]
) -> float:
    """
    Closeness centrality via NetworkX.
    Paper Eq. (2): C(v) = (|V|-1) / sum_{u≠v} d(v,u)
    """
    G = _build_graph(all_agents, interactions)
    if agent_id not in G:
        return 0.0
    scores = nx.closeness_centrality(G)
    return round(scores.get(agent_id, 0.0), 4)


def compute_brokerage_score(
    agent_id: str,
    all_agents: List[Dict],
    interactions: Dict[str, Dict[str, int]],
    clusters: List[Dict]
) -> float:
    """
    Fraction of cross-cluster interactions.
    Paper Eq. (3): Brok(v) = |{(v,u): cluster(v)≠cluster(u)}| / |{(v,u)}|
    """
    if not interactions.get(agent_id):
        return 0.0

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
        other_obj = next((a for a in all_agents if a["id"] == other_id), None)
        if other_obj and other_obj.get("cluster") != agent_cluster:
            cross_cluster_count += count

    if total_interactions == 0:
        return 0.0

    return round(cross_cluster_count / total_interactions, 4)


def compute_reciprocity(
    agent_id: str,
    all_agents: List[Dict],
    interactions: Dict[str, Dict[str, int]]
) -> float:
    """
    Reciprocity: fraction of bidirectional edges.
    Paper Eq. (4): Rec(v) = |{u: (v,u)∈E ∧ (u,v)∈E}| / |{u: (v,u)∈E ∨ (u,v)∈E}|
    """
    out_neighbors = set(interactions.get(agent_id, {}).keys())
    all_partners = set(out_neighbors)
    for other_id, other_interactions in interactions.items():
        if agent_id in other_interactions:
            all_partners.add(other_id)

    if not all_partners:
        return 0.0

    reciprocal = 0
    for u in all_partners:
        v_to_u = u in out_neighbors
        u_to_v = agent_id in interactions.get(u, {})
        if v_to_u and u_to_v:
            reciprocal += 1

    return round(reciprocal / len(all_partners), 4)


def compute_interaction_diversity(
    agent_id: str,
    interactions: Dict[str, Dict[str, int]]
) -> float:
    """
    Shannon entropy of interaction distribution, normalized by log2(k).
    Paper Eq. (5): H(v) = -Σ p_u * log2(p_u) / log2(k)
    """
    if not interactions.get(agent_id):
        return 0.0

    counts = list(interactions[agent_id].values())
    total = sum(counts)
    if total == 0:
        return 0.0

    k = len(counts)
    if k <= 1:
        return 0.0

    entropy = 0.0
    for c in counts:
        p = c / total
        if p > 0:
            entropy -= p * math.log2(p)

    max_entropy = math.log2(k)
    if max_entropy == 0:
        return 0.0

    return round(entropy / max_entropy, 4)


def compute_participation_balance(all_agents: List[Dict]) -> float:
    """
    Gini coefficient of turn distribution (0=equal, 1=dominated).
    """
    turn_counts = [a.get("turncount", 0) for a in all_agents]

    if not turn_counts or sum(turn_counts) == 0:
        return 0.0

    if len(turn_counts) == 1:
        return 0.0

    sorted_turns = sorted(turn_counts)
    n = len(sorted_turns)

    numerator = sum((i + 1) * turns for i, turns in enumerate(sorted_turns))
    denominator = n * sum(sorted_turns)

    if denominator == 0:
        return 0.0

    gini = 2 * numerator / denominator - (n + 1) / n
    return round(max(0.0, min(1.0, gini)), 4)


def compute_influence_score(agent: Dict) -> float:
    """Combined influence from turns, mentions, and connections."""
    base = 1.0
    base += agent.get("turncount", 0) * 0.1
    base += agent.get("mentions", {}).get("count", 0) * 0.15
    base += len(agent.get("interactions", {})) * 0.2

    valence = agent.get("valence", 0)
    base += max(0, valence) * 0.3

    return round(min(10.0, base), 4)


def compute_clustering_coefficient(
    agent_id: str,
    all_agents: List[Dict],
    interactions: Dict[str, Dict[str, int]]
) -> float:
    """
    Ratio of reciprocated edges to total edges (mutual / total).
    Paper: clustering coefficient as mutual interaction density.
    """
    out_edges = interactions.get(agent_id, {})
    out_neighbors = set(out_edges.keys())

    all_partners = set(out_neighbors)
    for other_id, other_interactions in interactions.items():
        if agent_id in other_interactions:
            all_partners.add(other_id)

    total_edges = len(all_partners)
    if total_edges == 0:
        return 0.0

    mutual = 0
    for u in all_partners:
        v_to_u = u in out_neighbors
        u_to_v = agent_id in interactions.get(u, {})
        if v_to_u and u_to_v:
            mutual += 1

    return round(mutual / total_edges, 4)


def compute_eigenvector_centrality(
    agent_id: str,
    all_agents: List[Dict],
    interactions: Dict[str, Dict[str, int]]
) -> float:
    """
    Weighted prestige from well-connected neighbors.
    Sum of neighbors' prestige weighted by interaction intensity.
    """
    G = _build_undirected(all_agents, interactions)
    if agent_id not in G:
        return 0.0

    try:
        scores = nx.eigenvector_centrality(G, max_iter=1000, tol=1e-06, weight="weight")
    except nx.PowerIterationFailedConvergence:
        return 0.0

    return round(scores.get(agent_id, 0.0), 4)


def compute_pagerank_proxy(betweenness_value: float, reciprocity_value: float) -> float:
    """
    Damped combination: 0.85 * betweenness + 0.15 * reciprocity.
    Paper: PageRank-like proxy blending flow control and mutual exchange.
    """
    return round(0.85 * betweenness_value + 0.15 * reciprocity_value, 4)


def compute_total_activity(
    agent_id: str,
    interactions: Dict[str, Dict[str, int]]
) -> float:
    """
    Total count of interaction objects: sum of all interaction values across partners.
    """
    partner_counts = interactions.get(agent_id, {})
    return float(sum(partner_counts.values()))


def compute_discourse_consistency(
    agent: Dict,
    interactions: Dict[str, Dict[str, int]]
) -> float:
    """
    How consistently the agent maintains the same interaction pattern.
    Approximated as 1 - normalized variance of interaction counts.
    """
    agent_id = agent["id"]
    counts = list(interactions.get(agent_id, {}).values())

    if len(counts) < 2:
        return 1.0

    mean_val = sum(counts) / len(counts)
    if mean_val == 0:
        return 1.0

    variance = sum((c - mean_val) ** 2 for c in counts) / len(counts)
    max_variance = mean_val ** 2

    if max_variance == 0:
        return 1.0

    normalized_var = min(1.0, math.sqrt(variance) / mean_val)
    return round(max(0.0, 1.0 - normalized_var), 4)


def compute_partner_reach(
    agent_id: str,
    interactions: Dict[str, Dict[str, int]]
) -> int:
    """
    Number of distinct interaction partners.
    """
    return len(interactions.get(agent_id, {}))


def compute_structural_holes(clustering_coefficient: float) -> float:
    """
    Complement of clustering coefficient.
    Paper: Burt's structural holes framework — 1 - clustering_coefficient.
    """
    return round(1.0 - clustering_coefficient, 4)


def compute_clustering_coefficient(
    agent_id: str,
    all_agents: List[Dict],
    interactions: Dict[str, Dict[str, int]]
) -> float:
    """Ratio of reciprocated to total interactions (local clustering proxy)."""
    out_neighbors = set(interactions.get(agent_id, {}).keys())
    if not out_neighbors:
        return 0.0
    mutual = 0
    for u in out_neighbors:
        if agent_id in interactions.get(u, {}):
            mutual += 1
    return round(mutual / len(out_neighbors), 4)


def compute_structural_holes(agent_id: str, all_agents: List[Dict],
                              interactions: Dict[str, Dict[str, int]]) -> float:
    """Brokerage opportunity: 1 - clustering_coefficient."""
    return round(1.0 - compute_clustering_coefficient(agent_id, all_agents, interactions), 4)


def compute_eigenvector_centrality(
    agent_id: str,
    all_agents: List[Dict],
    interactions: Dict[str, Dict[str, int]]
) -> float:
    """Eigenvector centrality proxy (weighted by reciprocal connections)."""
    G = _build_graph(all_agents, interactions)
    if agent_id not in G or len(G) < 2:
        return 0.0
    try:
        scores = nx.eigenvector_centrality_numpy(G, weight="weight", max_iter=100)
    except Exception:
        scores = {n: 0.0 for n in G.nodes()}
    return round(scores.get(agent_id, 0.0), 4)


def compute_pagerank_proxy(
    agent_id: str,
    all_agents: List[Dict],
    interactions: Dict[str, Dict[str, int]]
) -> float:
    """PageRank proxy: weighted combination of betweenness and reciprocity."""
    bc = compute_betweenness_centrality(agent_id, all_agents, interactions)
    rec = compute_reciprocity(agent_id, all_agents, interactions)
    return round(bc * 0.85 + rec * 0.15, 4)


def compute_total_activity(agent: Dict) -> float:
    """Normalized activity score from tokens, turns, and word count."""
    return round(min(1.0,
        agent.get("turn_count", 0) * 0.05 +
        agent.get("word_count", 0) * 0.001 +
        len(agent.get("interactions", {})) * 0.1), 4)


def compute_discourse_consistency(
    agent_id: str,
    all_agents: List[Dict],
    interactions: Dict[str, Dict[str, int]]
) -> float:
    """How consistent the agent's interaction patterns are (1 - normalized entropy)."""
    return round(1.0 - compute_interaction_diversity(agent_id, interactions), 4)


def compute_partner_reach(agent: Dict) -> float:
    """Fraction of all agents that this agent has interacted with."""
    return round(len(agent.get("interactions", {})) / max(len(agent.get("all_agents", [])), 1), 4)


# ── Graph builders ──────────────────────────────────────────────────────────

def _build_graph(all_agents: List[Dict],
                 interactions: Dict[str, Dict[str, int]]) -> nx.DiGraph:
    """Build a weighted directed interaction graph."""
    G = nx.DiGraph()
    agent_ids = {a["id"] for a in all_agents}
    G.add_nodes_from(agent_ids)
    for src, targets in interactions.items():
        for dst, weight in targets.items():
            if dst in agent_ids:
                G.add_edge(src, dst, weight=weight)
    return G


def _build_undirected(all_agents: List[Dict],
                      interactions: Dict[str, Dict[str, int]]) -> nx.Graph:
    """Build an undirected interaction graph."""
    G = nx.Graph()
    agent_ids = {a["id"] for a in all_agents}
    G.add_nodes_from(agent_ids)
    for src, targets in interactions.items():
        for dst, weight in targets.items():
            if dst in agent_ids:
                if G.has_edge(src, dst):
                    G[src][dst]["weight"] += weight
                else:
                    G.add_edge(src, dst, weight=weight)
    return G