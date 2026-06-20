"""Metric normalization and smoothing pipeline."""

import math
from typing import Dict, List, Any, Optional, Tuple
from statistics import median, stdev, mean


class NormalizationPipeline:
    """Normalize and smooth metric values across agents and time."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize normalization pipeline with config.

        Args:
            config: Configuration dict with normalization settings
        """
        self.config = config
        self.normalize_cfg = config.get("normalization", {})
        self.smooth_cfg = config.get("smoothing", {})

        # History for smoothing per metric
        self.history = {}
        self.smoothed_values = {}

    def percentile_normalize(
        self,
        value: float,
        all_values: List[float],
        floor_pct: int = 5,
        ceil_pct: int = 95
    ) -> float:
        """Normalize value to [0,1] using percentile method.

        Args:
            value: Value to normalize
            all_values: All values for percentile calculation
            floor_pct: Floor percentile (default 5)
            ceil_pct: Ceiling percentile (default 95)

        Returns:
            Normalized value in [0, 1]
        """
        if not all_values or len(all_values) == 0:
            return 0.5

        # Handle single value
        if len(all_values) == 1:
            return 0.5 if value == all_values[0] else 0

        # Calculate percentiles
        sorted_vals = sorted(all_values)
        n = len(sorted_vals)
        floor_idx = max(0, int(n * floor_pct / 100))
        ceil_idx = min(n - 1, int(n * ceil_pct / 100))

        floor_val = sorted_vals[floor_idx]
        ceil_val = sorted_vals[ceil_idx]

        # Clamp to bounds
        if ceil_val == floor_val:
            return 0.5

        normalized = (value - floor_val) / (ceil_val - floor_val)

        # Clamp to [0, 1]
        if self.normalize_cfg.get("clamp_to_bounds", True):
            normalized = max(0, min(1, normalized))

        return normalized

    def log_scale(self, value: float, base: float = 10) -> float:
        """Apply logarithmic scaling for exponential metrics.

        Args:
            value: Value to scale
            base: Logarithm base (default 10)

        Returns:
            Log-scaled value
        """
        if value <= 0:
            return 0
        return math.log(value + 1, base)

    def normalize_agent_metrics(
        self,
        agent: Dict[str, Any],
        all_agents: List[Dict[str, Any]],
        log_scale_metrics: Optional[List[str]] = None
    ) -> Dict[str, float]:
        """Normalize all metrics for an agent.

        Args:
            agent: Agent object with metric fields
            all_agents: All agents for percentile calculation
            log_scale_metrics: Metrics to apply log scaling to

        Returns:
            Dict of normalized metric values
        """
        normalized = {}
        log_scale_metrics = log_scale_metrics or self.normalize_cfg.get(
            "log_scale_metrics", []
        )

        # Define metric ranges for normalization
        metric_ranges = {
            # Social
            "influence": ("betweenness", 1),
            "betweennessproxy": ("betweennessproxy", 1),
            "interactiondensity": ("turn_count", 100),
            "discourseconsistency": ("consistency", 1),
            # Affective
            "valence": ("valence", 2),  # range -1 to 1
            "arousal": ("arousal", 1),
            "dominance": ("dominance", 1),
            "emotiondiversity": ("emotiondiversity", 1),
            # Operational
            "tokensperturn": ("tokens", 1000),
            "costperturn": ("cost_per_turn", 0.1),
            "latencymedian": ("latency", 5000),
            "promptcompletionratio": ("pc_ratio", 2),
            # Debate
            "stance": ("stance", 2),  # range -1 to 1
            "consensusalignment": ("consensus", 1),
        }

        for metric_name, (field_name, max_val) in metric_ranges.items():
            raw_val = agent.get(field_name, 0)

            # Collect all values for percentile
            all_values = [a.get(field_name, 0) for a in all_agents]

            # Apply log scaling if needed
            if metric_name in log_scale_metrics:
                raw_val = self.log_scale(raw_val)
                all_values = [self.log_scale(v) for v in all_values]

            # Normalize
            if metric_name in ["valence", "stance"]:
                # Already in [-1, 1] range, convert to [0, 1]
                normalized[metric_name] = (raw_val + 1) / 2
            else:
                # Use percentile normalization
                normalized[metric_name] = self.percentile_normalize(
                    raw_val, all_values
                )

        return normalized

    def smooth_value(
        self,
        metric_id: str,
        new_value: float,
        alpha: Optional[float] = None,
        window_size: Optional[int] = None
    ) -> float:
        """Apply exponential moving average smoothing.

        Args:
            metric_id: Unique ID for this metric (e.g., "agent_123_influence")
            new_value: New raw value
            alpha: Smoothing factor (0=no smoothing, 1=use new value immediately)
            window_size: For reference (not used in EMA)

        Returns:
            Smoothed value
        """
        alpha = alpha or self.smooth_cfg.get("alpha", 0.3)

        if metric_id not in self.smoothed_values:
            # First value
            self.smoothed_values[metric_id] = new_value
            if metric_id not in self.history:
                self.history[metric_id] = [new_value]
            return new_value

        # EMA: smoothed = alpha * new + (1 - alpha) * previous
        prev_smoothed = self.smoothed_values[metric_id]
        smoothed = alpha * new_value + (1 - alpha) * prev_smoothed

        # Store smoothed value
        self.smoothed_values[metric_id] = smoothed

        # Keep history (limited)
        if metric_id not in self.history:
            self.history[metric_id] = []
        self.history[metric_id].append(smoothed)

        # Limit history size
        max_history = window_size or self.smooth_cfg.get("window_size", 50)
        if len(self.history[metric_id]) > max_history:
            self.history[metric_id] = self.history[metric_id][-max_history:]

        return smoothed

    def get_metric_variance(
        self,
        metric_id: str,
        window_size: Optional[int] = None
    ) -> float:
        """Get variance of metric over recent history.

        Args:
            metric_id: Metric identifier
            window_size: Number of recent values to consider

        Returns:
            Variance (0 if not enough data)
        """
        if metric_id not in self.history or len(self.history[metric_id]) < 2:
            return 0

        window_size = window_size or self.smooth_cfg.get("window_size", 20)
        recent = self.history[metric_id][-window_size:]

        if len(recent) < 2:
            return 0

        return stdev(recent) if len(recent) > 1 else 0

    def get_metric_trend(
        self,
        metric_id: str,
        window_size: int = 5
    ) -> float:
        """Get trend direction of metric.

        Args:
            metric_id: Metric identifier
            window_size: Number of recent values to compare

        Returns:
            Trend: -1 (decreasing), 0 (stable), +1 (increasing)
        """
        if metric_id not in self.history or len(self.history[metric_id]) < 2:
            return 0

        recent = self.history[metric_id][-window_size:]

        if len(recent) < 2:
            return 0

        avg_first_half = mean(recent[:len(recent)//2])
        avg_second_half = mean(recent[len(recent)//2:])

        diff = avg_second_half - avg_first_half

        if abs(diff) < 0.01:  # Stable
            return 0
        elif diff > 0:  # Increasing
            return 1
        else:  # Decreasing
            return -1

    def reset_metric_history(self, metric_id: str):
        """Reset history for a specific metric.

        Args:
            metric_id: Metric identifier
        """
        if metric_id in self.history:
            del self.history[metric_id]
        if metric_id in self.smoothed_values:
            del self.smoothed_values[metric_id]

    def reset_all_history(self):
        """Reset all metric history (e.g., when loading new preset)."""
        self.history.clear()
        self.smoothed_values.clear()


class MetricAggregator:
    """Aggregate metrics across agents for cluster/global views."""

    @staticmethod
    def aggregate_metric(
        agent_values: Dict[str, float],
        method: str = "mean"
    ) -> float:
        """Aggregate metric from multiple agents.

        Args:
            agent_values: Dict of agent_id -> metric_value
            method: Aggregation method (mean, median, max, min, sum)

        Returns:
            Aggregated value
        """
        if not agent_values:
            return 0

        values = list(agent_values.values())

        if method == "mean":
            return mean(values)
        elif method == "median":
            return median(values)
        elif method == "max":
            return max(values)
        elif method == "min":
            return min(values)
        elif method == "sum":
            return sum(values)
        else:
            return mean(values)  # Default

    @staticmethod
    def compute_cluster_metric(
        agents: List[Dict[str, Any]],
        metric_field: str,
        method: str = "mean"
    ) -> float:
        """Compute cluster-level metric.

        Args:
            agents: List of agent objects
            metric_field: Metric field name
            method: Aggregation method

        Returns:
            Cluster metric value
        """
        values = {a["id"]: a.get(metric_field, 0) for a in agents if "id" in a}
        return MetricAggregator.aggregate_metric(values, method)

    @staticmethod
    def compute_emotion_diversity(
        emotion_dict: Dict[str, float],
        base: float = 2
    ) -> float:
        """Compute Shannon entropy for emotion diversity.

        Args:
            emotion_dict: Dict of emotion -> intensity
            base: Log base (default 2 for bits)

        Returns:
            Shannon entropy
        """
        if not emotion_dict or sum(emotion_dict.values()) == 0:
            return 0

        total = sum(emotion_dict.values())
        entropy = 0

        for intensity in emotion_dict.values():
            if intensity > 0:
                p = intensity / total
                entropy -= p * math.log(p, base)

        return entropy
