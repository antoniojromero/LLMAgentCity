"""Unified metrics computation engine integrating all metric modules."""

from typing import Dict, List, Tuple, Any
import sys
from pathlib import Path

# Import metric modules
from ..metrics import (
    social, affective, operational,
    conversation, developer, debate
)


class MetricsEngine:
    """Compute and manage all agent metrics across views."""

    def __init__(self):
        """Initialize metrics engine."""
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
        """
        Compute all derived metrics for an agent.

        Args:
            agent: Agent object
            all_agents: All agents in simulation
            interactions: Interaction graph
            clusters: Cluster definitions
            mode: Simulation mode (conversation, debate, developer)

        Returns:
            dict: Updated agent with all computed metrics
        """
        agent_id = agent["id"]

        # SOCIAL METRICS
        agent["betweennessproxy"] = social.compute_betweenness_centrality(
            agent_id, all_agents, interactions
        )
        agent["brokeragescore"] = social.compute_brokerage_score(
            agent_id, all_agents, interactions, clusters
        )

        # AFFECTIVE METRICS
        detected_emotions = agent.get("detected_emotions", {})
        agent["emotiondiversity"] = affective.compute_emotion_diversity(
            detected_emotions
        )
        agent["dominantemotion"] = affective.compute_dominant_emotion(
            detected_emotions
        )

        arousal_history = agent.get("arousalhistory", [])
        agent["arousalvariance"] = affective.compute_arousal_variance(
            arousal_history
        )

        agent["emotioncontagionslope"] = affective.compute_emotion_contagion(
            agent_id, all_agents, agent.get("messagehistory", []), interactions
        )

        # OPERATIONAL METRICS
        agent["costperturn"] = operational.compute_cost_per_turn(agent)
        agent["latencyvariance"] = operational.compute_latency_variance(
            agent.get("latencysamples", [])
        )
        agent["promptcompletionratio"] = operational.compute_prompt_completion_ratio(
            agent
        )

        # CONVERSATION METRICS
        message_history = agent.get("messagehistory", [])
        if message_history:
            latest_message = message_history[-1] if message_history else ""
            agent["speechacts"] = conversation.classify_speech_acts(latest_message)
            agent["lexicaldiversity"] = conversation.compute_lexical_diversity(
                message_history
            )

        # DEVELOPER METRICS (if in developer mode)
        if mode == "developer":
            detected_files = agent.get("detected_files", [])
            agent["taskphasecounts"] = developer.classify_task_phase(
                message_history[-1] if message_history else ""
            )
            agent["crossfilecoordination"] = developer.compute_cross_file_coordination(
                detected_files if isinstance(detected_files, list) else []
            )

        # DEBATE METRICS (if in debate mode)
        if mode == "debate":
            latest_message = message_history[-1] if message_history else ""
            agent["stance"] = debate.estimate_stance(latest_message)
            agent["stanceshift"] = debate.compute_stance_shift(
                agent.get("stancehistory", [])
            )

        return agent

    def compute_global_metrics(
        self,
        all_agents: List[Dict],
        clusters: List[Dict],
        mode: str = "conversation"
    ) -> Dict[str, Any]:
        """
        Compute global (cluster-level, all-agent) metrics.

        Args:
            all_agents: All agents
            clusters: Cluster definitions
            mode: Simulation mode

        Returns:
            dict: Global metrics
        """
        global_metrics = {
            "participationbalance": social.compute_participation_balance(all_agents),
            "emotiondiversity": affective.compute_emotion_diversity(
                {e: sum(a.get("detected_emotions", {}).get(e, 0) for a in all_agents)
                 for e in set(e for a in all_agents for e in a.get("detected_emotions", {}))}
            ),
        }

        # Debate-specific global metrics
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
        """
        Extend snapshot with new metric fields.

        Args:
            snapshot: Existing snapshot
            all_agents: Current agent states
            clusters: Current clusters
            mode: Simulation mode

        Returns:
            dict: Enhanced snapshot with new fields
        """
        # Update agent metrics in snapshot
        for agent_id, agent_snap in snapshot.get("agents", {}).items():
            # Find full agent object
            full_agent = next(
                (a for a in all_agents if a["id"] == agent_id),
                None
            )

            if full_agent:
                # Copy new metric fields
                for metric in [
                    "betweennessproxy", "brokeragescore",
                    "emotiondiversity", "dominantemotion", "arousalvariance",
                    "emotioncontagionslope",
                    "costperturn", "latencyvariance", "promptcompletionratio",
                    "speechacts", "lexicaldiversity",
                    "taskphasecounts", "crossfilecoordination",
                    "stance", "stanceshift"
                ]:
                    agent_snap[metric] = full_agent.get(metric, None)

        # Add global metrics
        snapshot["globalmetrics"] = self.compute_global_metrics(
            all_agents, clusters, mode
        )

        return snapshot


# Singleton instance
engine = MetricsEngine()


def compute_metrics(agent, all_agents, interactions, clusters, mode="conversation"):
    """Convenience function."""
    return engine.compute_agent_metrics(agent, all_agents, interactions, clusters, mode)


def compute_global(all_agents, clusters, mode="conversation"):
    """Convenience function."""
    return engine.compute_global_metrics(all_agents, clusters, mode)


def extend_snap(snapshot, all_agents, clusters, mode="conversation"):
    """Convenience function."""
    return engine.extend_snapshot(snapshot, all_agents, clusters, mode)
