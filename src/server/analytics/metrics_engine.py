"""Unified metrics computation engine integrating all metric modules."""

from typing import Dict, List, Any
import sys
from pathlib import Path

from ..metrics import (
    social, affective, operational,
    conversation, developer, debate
)


class MetricsEngine:
    """Compute and manage all agent metrics across views."""

    def __init__(self):
        self.metric_modules = {
            'social': social,
            'affective': affective,
            'operational': operational,
            'conversation': conversation,
            'developer': developer,
            'debate': debate,
        }

    def compute_agent_metrics(
        self,
        agent: Dict[str, Any],
        all_agents: List[Dict],
        interactions: Dict[str, Dict[str, int]],
        clusters: List[Dict],
        mode: str = "conversation"
    ) -> Dict[str, Any]:
        agent_id = agent["id"]

        # ── SOCIAL METRICS ────────────────────────────────────────────────
        agent["betweennessproxy"] = social.compute_betweenness_centrality(
            agent_id, all_agents, interactions
        )
        agent["reciprocal"] = social.compute_reciprocity(
            agent_id, all_agents, interactions
        )
        agent["structural_holes"] = social.compute_structural_holes(
            agent_id, all_agents, interactions
        )
        agent["closeness_centrality"] = social.compute_closeness_centrality(
            agent_id, all_agents, interactions
        )
        agent["response_diversity"] = social.compute_interaction_diversity(
            agent_id, interactions
        )
        agent["partner_count"] = len(interactions.get(agent_id, {}))
        agent["clustering_coefficient"] = social.compute_clustering_coefficient(
            agent_id, all_agents, interactions
        )
        agent["eigenvector_centrality"] = social.compute_eigenvector_centrality(
            agent_id, all_agents, interactions
        )
        agent["pagerank_proxy"] = social.compute_pagerank_proxy(
            agent_id, all_agents, interactions
        )
        agent["brokeragescore"] = social.compute_brokerage_score(
            agent_id, all_agents, interactions, clusters
        )
        agent["total_activity"] = social.compute_total_activity(agent)
        agent["discourse_consistency"] = social.compute_discourse_consistency(
            agent_id, all_agents, interactions
        )
        agent["partner_reach"] = social.compute_partner_reach(agent)
        agent["overall_influence"] = social.compute_influence_score(agent)

        # ── AFFECTIVE METRICS ─────────────────────────────────────────────
        detected_emotions = agent.get("detected_emotions", {})
        emotion_counts = {}
        for emo, data in detected_emotions.items():
            if isinstance(data, dict):
                emotion_counts[emo] = data.get("count", 0)
            elif isinstance(data, (int, float)):
                emotion_counts[emo] = int(data)
            else:
                emotion_counts[emo] = 0

        agent["emotiondiversity"] = affective.compute_emotion_diversity(
            detected_emotions
        )
        agent["dominance"] = agent.get("dominance", 0)

        arousal_history = agent.get("arousal_history", [])
        agent["arousalvariance"] = affective.compute_arousal_variance(
            arousal_history
        )

        valence_history = agent.get("valence_history", [])
        agent["valence_volatility"] = affective.compute_valence_volatility(
            valence_history
        )
        agent["sentiment_drift"] = affective.compute_sentiment_drift(
            valence_history
        )

        group_valence = [ag.get("valence", 0) for ag in all_agents] if all_agents else []
        agent["polarity_mismatch"] = affective.compute_polarity_alignment(
            valence_history, group_valence
        )

        agent["affective_influence"] = affective.compute_affective_influence(
            agent.get("sentiment_drift", 0),
            agent.get("betweennessproxy", 0)
        )

        agent["emotioncontagion"] = affective.compute_emotion_contagion(
            agent_id, all_agents,
            agent.get("message_history", []),
            interactions
        )

        latest_text = ""
        if agent.get("message_history"):
            latest_msg = agent["message_history"][-1]
            if isinstance(latest_msg, dict):
                latest_text = latest_msg.get("text", "")
        agent["toxicity_score"] = affective.compute_toxicity_score(
            agent.get("valence", 0), agent.get("arousal", 0), latest_text
        )

        agent["emotional_inertia"] = affective.compute_emotional_inertia(
            valence_history
        )
        agent["emotion_count"] = affective.compute_emotion_count(
            detected_emotions
        )
        agent["emotion_variety"] = affective.compute_emotion_variety(
            detected_emotions
        )

        # ── OPERATIONAL METRICS ───────────────────────────────────────────
        agent["costperturn"] = operational.compute_cost_per_turn(agent)
        agent["token_efficiency"] = operational.compute_token_efficiency(agent)

        latency_samples = agent.get("latency_samples", [])
        agent["avg_latency_ms"] = operational.compute_average_latency(agent)
        agent["throughput"] = operational.compute_throughput(agent)
        agent["latencyvariance"] = operational.compute_latency_variance(
            latency_samples
        )
        agent["context_utilization"] = operational.compute_context_utilization(
            agent
        )
        agent["promptcompletionratio"] = operational.compute_prompt_completion_ratio(
            agent
        )

        message_history = agent.get("message_history", [])
        agent["costvariance"] = operational.compute_cost_variance(
            message_history
        )
        agent["retry_rate"] = operational.compute_retry_rate(
            agent.get("latencyvariance", 0)
        )
        agent["cost_var_type_stability"] = operational.compute_cost_stability(
            agent.get("costvariance", 0)
        )
        agent["generation_rate"] = operational.compute_generation_rate(
            agent.get("throughput", 0)
        )
        agent["response_speed"] = operational.compute_response_speed(
            agent.get("avg_latency_ms", 0)
        )
        agent["cost_efficiency"] = operational.compute_cost_efficiency(
            agent.get("costperturn", 0)
        )

        # ── COORDINATION METRICS (debate) ─────────────────────────────────
        word_count = agent.get("word_count", 0)
        turn_count = agent.get("turn_count", 0)
        agent["argument_strength"] = debate.compute_argument_strength(
            word_count, turn_count
        )
        agent["planning_load"] = debate.compute_planning_load(agent)
        agent["review_depth"] = debate.compute_review_depth(
            agent.get("argument_score", 0), turn_count
        )

        total_turns = sum(ag.get("turn_count", 0) for ag in all_agents) if all_agents else 1
        agent["turn_taking_equity"] = debate.compute_turn_taking_equity(
            turn_count, total_turns, max(len(all_agents), 1)
        )
        agent["stance_intensity"] = debate.compute_stance_intensity(
            detected_emotions
        )
        agent["initiative_ratio"] = debate.compute_initiative_ratio(
            agent.get("valence_history", [])
        )

        agent["delegation_load"] = debate.compute_delegation_load(
            agent.get("planning_load", 0), latest_text
        )
        agent["convergence_contribution"] = debate.compute_convergence_contribution(
            agent.get("polarity_mismatch", 0.5)
        )
        agent["consensus_alignment"] = debate.compute_consensus_alignment(
            agent.get("valence", 0),
            [ag.get("valence", 0) for ag in all_agents]
        )

        agent["xref_load"] = debate.compute_xref_load(
            message_history
        )

        return agent

    def compute_global_metrics(
        self,
        all_agents: List[Dict],
        clusters: List[Dict],
        mode: str = "conversation"
    ) -> Dict[str, Any]:
        global_metrics = {
            "participationbalance": social.compute_participation_balance(all_agents),
            "emotiondiversity": affective.compute_emotion_diversity(
                {e: sum(a.get("detected_emotions", {}).get(e, 0) for a in all_agents)
                 for e in set(e for a in all_agents for e in a.get("detected_emotions", {}))}
            ),
        }

        if mode == "debate":
            stances = [a.get("stance", 0) for a in all_agents]
            global_metrics["polarization"] = debate.compute_polarization_index(stances)
            global_metrics["consensusalignment"] = sum(
                debate.compute_consensus_alignment(a.get("stance", 0), stances)
                for a in all_agents
            ) / max(1, len(all_agents))

        return global_metrics

    def extend_snapshot(
        self,
        snapshot: Dict[str, Any],
        all_agents: List[Dict],
        clusters: List[Dict],
        mode: str = "conversation"
    ) -> Dict[str, Any]:
        for agent_id, agent_snap in snapshot.get("agents", {}).items():
            full_agent = next(
                (a for a in all_agents if a["id"] == agent_id),
                None
            )

            if full_agent:
                for metric in [
                    "betweennessproxy", "brokeragescore",
                    "reciprocal", "structural_holes",
                    "closeness_centrality", "response_diversity",
                    "partner_count", "clustering_coefficient",
                    "eigenvector_centrality", "pagerank_proxy",
                    "total_activity", "discourse_consistency",
                    "partner_reach", "overall_influence",
                    "emotiondiversity", "dominance",
                    "arousalvariance", "valence_volatility",
                    "sentiment_drift", "polarity_mismatch",
                    "affective_influence", "emotioncontagion",
                    "toxicity_score", "emotional_inertia",
                    "emotion_count", "emotion_variety",
                    "costperturn", "token_efficiency",
                    "avg_latency_ms", "throughput",
                    "latencyvariance", "context_utilization",
                    "promptcompletionratio", "costvariance",
                    "retry_rate", "cost_var_type_stability",
                    "generation_rate", "response_speed",
                    "cost_efficiency",
                    "argument_strength", "planning_load",
                    "review_depth", "turn_taking_equity",
                    "stance_intensity", "initiative_ratio",
                    "delegation_load", "convergence_contribution",
                    "consensus_alignment", "xref_load",
                ]:
                    agent_snap[metric] = full_agent.get(metric, None)

        snapshot["globalmetrics"] = self.compute_global_metrics(
            all_agents, clusters, mode
        )

        return snapshot


engine = MetricsEngine()


def compute_metrics(agent, all_agents, interactions, clusters, mode="conversation"):
    return engine.compute_agent_metrics(agent, all_agents, interactions, clusters, mode)


def compute_global(all_agents, clusters, mode="conversation"):
    return engine.compute_global_metrics(all_agents, clusters, mode)


def extend_snap(snapshot, all_agents, clusters, mode="conversation"):
    return engine.extend_snapshot(snapshot, all_agents, clusters, mode)