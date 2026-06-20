"""Integration of metrics engine with server simulation loop."""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional

from .normalization import NormalizationPipeline, MetricAggregator
from ..analytics.metrics_engine import MetricsEngine


class MetricsIntegration:
    """Manage metrics throughout server simulation lifecycle."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize metrics integration.

        Args:
            config_path: Path to metrics_config.json
        """
        self.engine = MetricsEngine()
        self.config = self._load_config(config_path)
        self.pipeline = NormalizationPipeline(self.config)
        self.current_preset = "default"

        # Cache for aggregated metrics
        self.cluster_metrics_cache = {}
        self.global_metrics_cache = {}

    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """Load metrics configuration.

        Args:
            config_path: Path to config file

        Returns:
            Configuration dict
        """
        if config_path is None:
            # Look for config relative to this file
            base = Path(__file__).parent.parent.parent.parent
            config_path = base / "config" / "metrics_config.json"

        if not config_path or not Path(config_path).exists():
            # Return default config
            return {
                "global": {
                    "smoothing_alpha": 0.3,
                    "window_size": 20,
                    "normalization_percentile": 5,
                    "max_percentile": 95
                },
                "normalization": {"log_scale_metrics": []},
                "smoothing": {"alpha": 0.3, "window_size": 20}
            }

        with open(config_path) as f:
            return json.load(f)

    def set_preset(self, preset_name: str):
        """Switch to a preset configuration.

        Args:
            preset_name: Name of preset (default, sensitive, stable, realtime)
        """
        if preset_name in self.config.get("presets", {}):
            self.current_preset = preset_name
            # Reset smoothing history on preset change
            self.pipeline.reset_all_history()

    def compute_agent_metrics(
        self,
        agent: Dict[str, Any],
        all_agents: List[Dict[str, Any]],
        interactions: Dict[str, Dict[str, int]],
        clusters: List[Dict[str, Any]],
        mode: str = "conversation",
        apply_normalization: bool = True,
        apply_smoothing: bool = True
    ) -> Dict[str, Any]:
        """Compute metrics for an agent.

        Args:
            agent: Agent object
            all_agents: All agents in simulation
            interactions: Interaction graph
            clusters: Cluster definitions
            mode: Simulation mode (conversation, debate, developer)
            apply_normalization: Whether to normalize metrics
            apply_smoothing: Whether to smooth metrics

        Returns:
            Updated agent with computed metrics
        """
        # Compute raw metrics
        agent = self.engine.compute_agent_metrics(
            agent, all_agents, interactions, clusters, mode
        )

        # Apply normalization
        if apply_normalization:
            agent = self._apply_normalization(agent, all_agents)

        # Apply smoothing
        if apply_smoothing:
            agent = self._apply_smoothing(agent)

        # Add normalized variants
        agent["_normalized"] = {k: agent.get(f"{k}_normalized", 0)
                                for k in ["influence", "arousal", "costperturn"]}

        return agent

    def _apply_normalization(
        self,
        agent: Dict[str, Any],
        all_agents: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Apply normalization to agent metrics.

        Args:
            agent: Agent with raw metrics
            all_agents: All agents for percentile calculation

        Returns:
            Agent with added _normalized fields
        """
        # Get current preset
        preset = self.config.get("presets", {}).get(
            self.current_preset, {}
        )

        # Define metrics to normalize
        metrics_to_normalize = {
            "betweennessproxy": [a.get("betweennessproxy", 0) for a in all_agents],
            "arousal": [a.get("arousal", 0) for a in all_agents],
            "valence": [a.get("valence", 0) for a in all_agents],
            "costperturn": [a.get("costperturn", 0) for a in all_agents],
            "emotiondiversity": [a.get("emotiondiversity", 0) for a in all_agents],
            "stance": [a.get("stance", 0) for a in all_agents],
        }

        # Normalize each metric
        for metric_name, all_values in metrics_to_normalize.items():
            raw_value = agent.get(metric_name, 0)

            # Handle special cases
            if metric_name in ["valence", "stance"]:
                # Already in [-1, 1], convert to [0, 1]
                norm_value = (raw_value + 1) / 2
            else:
                # Use percentile normalization
                norm_value = self.pipeline.percentile_normalize(
                    raw_value, all_values,
                    preset.get("global", {}).get("normalization_percentile", 5),
                    preset.get("global", {}).get("max_percentile", 95)
                )

            agent[f"{metric_name}_normalized"] = norm_value

        return agent

    def _apply_smoothing(self, agent: Dict[str, Any]) -> Dict[str, Any]:
        """Apply smoothing to agent metrics.

        Args:
            agent: Agent with metrics

        Returns:
            Agent with smoothed values
        """
        preset = self.config.get("presets", {}).get(
            self.current_preset, {}
        )
        alpha = preset.get("global", {}).get("smoothing_alpha", 0.3)
        window_size = preset.get("global", {}).get("window_size", 20)

        # Metrics to smooth
        metrics_to_smooth = [
            "betweennessproxy", "arousal", "valence", "costperturn",
            "emotiondiversity", "stance", "turn_count", "latency"
        ]

        for metric_name in metrics_to_smooth:
            if metric_name in agent and agent[metric_name] is not None:
                metric_id = f"{agent['id']}_{metric_name}"
                smoothed = self.pipeline.smooth_value(
                    metric_id, agent[metric_name],
                    alpha=alpha, window_size=window_size
                )
                agent[f"{metric_name}_smoothed"] = smoothed

        return agent

    def compute_cluster_metrics(
        self,
        cluster_name: str,
        agents: List[Dict[str, Any]],
        all_agents: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """Compute aggregated metrics for a cluster.

        Args:
            cluster_name: Cluster identifier
            agents: Agents in this cluster
            all_agents: All agents for comparison

        Returns:
            Cluster-level metrics
        """
        metrics = {}

        # Social metrics
        metrics["avg_influence"] = MetricAggregator.compute_cluster_metric(
            agents, "betweennessproxy", "mean"
        )
        metrics["interaction_density"] = sum(a.get("turn_count", 0) for a in agents)

        # Affective metrics
        metrics["avg_arousal"] = MetricAggregator.compute_cluster_metric(
            agents, "arousal", "mean"
        )
        metrics["avg_valence"] = MetricAggregator.compute_cluster_metric(
            agents, "valence", "mean"
        )

        # Operational metrics
        metrics["total_cost"] = sum(a.get("total_cost_usd", 0) for a in agents)
        metrics["avg_latency"] = MetricAggregator.compute_cluster_metric(
            agents, "avg_latency_ms", "median"
        )

        return metrics

    def compute_global_metrics(
        self,
        all_agents: List[Dict[str, Any]],
        clusters: List[Dict[str, Any]],
        mode: str = "conversation"
    ) -> Dict[str, Any]:
        """Compute global metrics across all agents.

        Args:
            all_agents: All agents
            clusters: All clusters
            mode: Simulation mode

        Returns:
            Global metrics dict
        """
        return self.engine.compute_global_metrics(all_agents, clusters, mode)

    def extend_snapshot(
        self,
        snapshot: Dict[str, Any],
        all_agents: List[Dict[str, Any]],
        clusters: List[Dict[str, Any]],
        mode: str = "conversation"
    ) -> Dict[str, Any]:
        """Extend a snapshot with metric data.

        Args:
            snapshot: Existing snapshot
            all_agents: Current agent states
            clusters: Current clusters
            mode: Simulation mode

        Returns:
            Enhanced snapshot
        """
        return self.engine.extend_snapshot(
            snapshot, all_agents, clusters, mode
        )

    def reset_metrics(self):
        """Reset metrics state (for preset switching or replay)."""
        self.pipeline.reset_all_history()
        self.cluster_metrics_cache.clear()
        self.global_metrics_cache.clear()

    def get_metric_status(self, agent_id: str) -> Dict[str, Any]:
        """Get current metric status for an agent.

        Args:
            agent_id: Agent ID

        Returns:
            Status dict with variance, trend, smoothed values
        """
        status = {}

        key_metrics = [
            "influence", "arousal", "valence", "costperturn"
        ]

        for metric in key_metrics:
            metric_id = f"{agent_id}_{metric}"
            status[metric] = {
                "smoothed": self.pipeline.smoothed_values.get(metric_id, 0),
                "variance": self.pipeline.get_metric_variance(metric_id),
                "trend": self.pipeline.get_metric_trend(metric_id),
            }

        return status


# Global instance
metrics_integration = None


def initialize_metrics(config_path: Optional[str] = None):
    """Initialize global metrics integration.

    Args:
        config_path: Path to metrics_config.json
    """
    global metrics_integration
    metrics_integration = MetricsIntegration(config_path)


def get_metrics() -> MetricsIntegration:
    """Get global metrics integration instance.

    Returns:
        MetricsIntegration instance
    """
    global metrics_integration
    if metrics_integration is None:
        initialize_metrics()
    return metrics_integration
