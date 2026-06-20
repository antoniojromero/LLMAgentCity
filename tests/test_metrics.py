"""
Unit tests for metric calculators.

Tests cover all 6 metric modules with edge cases and known scenarios.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'server'))

import pytest
from metrics.social import (
    compute_betweenness_centrality,
    compute_brokerage_score,
    compute_participation_balance,
)
from metrics.affective import (
    compute_emotion_diversity,
    compute_dominant_emotion,
    compute_arousal_variance,
)
from metrics.operational import (
    compute_cost_per_turn,
    compute_latency_variance,
    compute_prompt_completion_ratio,
)
from metrics.conversation import (
    classify_speech_acts,
    compute_lexical_diversity,
)
from metrics.developer import (
    classify_task_phase,
    compute_cross_file_coordination,
)
from metrics.debate import (
    estimate_stance,
    compute_stance_shift,
    compute_consensus_alignment,
)


# ============================================================================
# SOCIAL METRICS TESTS
# ============================================================================

class TestSocialMetrics:
    """Tests for social metric calculators."""

    def test_betweenness_centrality_single_agent(self):
        """Single agent should have zero betweenness."""
        agents = {"a": {"id": "a"}}
        interactions = {}
        result = compute_betweenness_centrality(agents, interactions)
        assert result.get("a", 0) == 0

    def test_betweenness_centrality_bridge(self):
        """Agent with many cross-cluster links should have high betweenness."""
        agents = {
            "a": {"id": "a", "cluster": "c1"},
            "b": {"id": "b", "cluster": "c1"},
            "c": {"id": "c", "cluster": "c2"},
            "d": {"id": "d", "cluster": "c2"},
        }
        interactions = {
            "a": {"c": 5, "d": 5},  # Bridge
            "b": {},
            "c": {"a": 1},
            "d": {"a": 1},
        }
        result = compute_betweenness_centrality(agents, interactions)
        assert result["a"] > 0
        assert result.get("b", 0) == 0

    def test_brokerage_score_zero(self):
        """Agent with no cross-cluster interactions should have zero brokerage."""
        agent = {"id": "a", "cluster": "c1"}
        interactions = {"a": {}}
        clusters = {"c1": {}}
        result = compute_brokerage_score(agent, interactions, clusters)
        assert result == 0

    def test_brokerage_score_high(self):
        """Agent with many cross-cluster interactions should have high brokerage."""
        agent = {"id": "a", "cluster": "c1"}
        interactions = {
            "a": {"b": 10, "c": 10, "d": 10}  # 3 interactions
        }
        clusters = {"c1": {}, "c2": {}, "c3": {}, "c4": {}}
        result = compute_brokerage_score(agent, interactions, clusters)
        assert result > 0

    def test_participation_balance_single_agent(self):
        """Single agent should have balanced participation (no variance)."""
        agents = {"a": {"turncount": 5}}
        result = compute_participation_balance(agents)
        assert result == 0  # No variance with single agent

    def test_participation_balance_unequal(self):
        """Unequal turn counts should give high Gini."""
        agents = {
            "a": {"turncount": 10},
            "b": {"turncount": 1},
        }
        result = compute_participation_balance(agents)
        assert result > 0.5  # High inequality


# ============================================================================
# AFFECTIVE METRICS TESTS
# ============================================================================

class TestAffectiveMetrics:
    """Tests for affective metric calculators."""

    def test_emotion_diversity_single(self):
        """Single emotion should give low diversity."""
        emotions = {"joy": 10}
        result = compute_emotion_diversity(emotions)
        assert result < 0.5

    def test_emotion_diversity_uniform(self):
        """Uniform distribution should give high diversity."""
        emotions = {
            "joy": 5,
            "anger": 5,
            "sadness": 5,
            "fear": 5,
        }
        result = compute_emotion_diversity(emotions)
        assert result > 2.0  # Good diversity

    def test_dominant_emotion_clear(self):
        """Clearest emotion should be dominant."""
        emotions = {"joy": 100, "anger": 1, "sadness": 1}
        result = compute_dominant_emotion(emotions)
        assert result == "joy"

    def test_dominant_emotion_empty(self):
        """Empty emotions should return None."""
        emotions = {}
        result = compute_dominant_emotion(emotions)
        assert result is None

    def test_arousal_variance_single(self):
        """Single arousal sample should give zero variance."""
        history = [0.5]
        result = compute_arousal_variance(history)
        assert result == 0

    def test_arousal_variance_volatile(self):
        """High swing in arousal should give high variance."""
        history = [0.1, 0.9, 0.1, 0.9]
        result = compute_arousal_variance(history)
        assert result > 0.2


# ============================================================================
# OPERATIONAL METRICS TESTS
# ============================================================================

class TestOperationalMetrics:
    """Tests for operational metric calculators."""

    def test_cost_per_turn_single(self):
        """Single turn should have its cost as cost per turn."""
        agent = {"total_cost_usd": 0.10, "turncount": 1}
        result = compute_cost_per_turn(agent)
        assert abs(result - 0.10) < 0.01

    def test_cost_per_turn_multiple(self):
        """Multiple turns should divide total cost."""
        agent = {"total_cost_usd": 1.00, "turncount": 10}
        result = compute_cost_per_turn(agent)
        assert abs(result - 0.10) < 0.01

    def test_cost_per_turn_zero_turns(self):
        """Zero turns should default to cost value."""
        agent = {"total_cost_usd": 0.05, "turncount": 0}
        result = compute_cost_per_turn(agent)
        assert result == 0.05

    def test_latency_variance_empty(self):
        """Empty latency should give zero."""
        latencies = []
        result = compute_latency_variance(latencies)
        assert result == 0

    def test_latency_variance_consistent(self):
        """Consistent latency should give zero variance."""
        latencies = [100, 100, 100, 100]
        result = compute_latency_variance(latencies)
        assert result < 0.1

    def test_prompt_completion_ratio_balanced(self):
        """Equal prompt and completion tokens should give 1.0."""
        agent = {"prompttokens": 100, "completiontokens": 100}
        result = compute_prompt_completion_ratio(agent)
        assert abs(result - 1.0) < 0.1

    def test_prompt_completion_ratio_zero_completion(self):
        """Zero completion tokens should default to 1.0."""
        agent = {"prompttokens": 100, "completiontokens": 0}
        result = compute_prompt_completion_ratio(agent)
        assert result == 1.0


# ============================================================================
# CONVERSATION METRICS TESTS
# ============================================================================

class TestConversationMetrics:
    """Tests for conversation metric calculators."""

    def test_classify_speech_acts_question(self):
        """Questions should be detected."""
        text = "What do you think about this proposal?"
        result = classify_speech_acts(text)
        assert result.get("question", 0) > 0

    def test_classify_speech_acts_proposal(self):
        """Proposals should be detected."""
        text = "I suggest we implement this feature."
        result = classify_speech_acts(text)
        assert result.get("proposal", 0) > 0

    def test_classify_speech_acts_agreement(self):
        """Agreement should be detected."""
        text = "I completely agree with your point."
        result = classify_speech_acts(text)
        assert result.get("agreement", 0) > 0

    def test_classify_speech_acts_disagreement(self):
        """Disagreement should be detected."""
        text = "I respectfully disagree with that approach."
        result = classify_speech_acts(text)
        assert result.get("disagreement", 0) > 0

    def test_lexical_diversity_empty(self):
        """Empty text should give zero diversity."""
        text = ""
        result = compute_lexical_diversity(text)
        assert result == 0

    def test_lexical_diversity_repetitive(self):
        """Repetitive text should give low diversity."""
        text = "word word word word word"
        result = compute_lexical_diversity(text)
        assert result < 0.5

    def test_lexical_diversity_varied(self):
        """Varied text should give high diversity."""
        text = "apple banana cherry dragon elephant fish giraffe"
        result = compute_lexical_diversity(text)
        assert result > 0.8


# ============================================================================
# DEVELOPER METRICS TESTS
# ============================================================================

class TestDeveloperMetrics:
    """Tests for developer metric calculators."""

    def test_classify_task_phase_planning(self):
        """Planning keywords should be detected."""
        text = "We need to design the architecture first."
        result = classify_task_phase(text)
        assert result.get("planning", 0) > 0

    def test_classify_task_phase_implementation(self):
        """Implementation keywords should be detected."""
        text = "Let me write the code for this feature."
        result = classify_task_phase(text)
        assert result.get("implementation", 0) > 0

    def test_classify_task_phase_debug(self):
        """Debug keywords should be detected."""
        text = "I found the bug in the error handling."
        result = classify_task_phase(text)
        assert result.get("debugging", 0) > 0

    def test_classify_task_phase_review(self):
        """Review keywords should be detected."""
        text = "Can you review my code changes?"
        result = classify_task_phase(text)
        assert result.get("review", 0) > 0

    def test_cross_file_coordination_none(self):
        """No file mentions should give zero."""
        history = []
        result = compute_cross_file_coordination(history)
        assert result == 0

    def test_cross_file_coordination_single(self):
        """Single file mention should give zero (no coordination)."""
        history = ["I modified main.py"]
        result = compute_cross_file_coordination(history)
        assert result == 0

    def test_cross_file_coordination_cross(self):
        """Multiple file mentions should give coordination score."""
        history = [
            "I modified main.py and utils.py together",
            "The API in server.py calls the function in models.py",
        ]
        result = compute_cross_file_coordination(history)
        assert result > 0


# ============================================================================
# DEBATE METRICS TESTS
# ============================================================================

class TestDebateMetrics:
    """Tests for debate metric calculators."""

    def test_estimate_stance_support(self):
        """Support keywords should give positive stance."""
        text = "I strongly agree with this proposal. It's excellent."
        result = estimate_stance(text)
        assert result > 0.3

    def test_estimate_stance_oppose(self):
        """Opposition keywords should give negative stance."""
        text = "I completely disagree. This is a terrible idea."
        result = estimate_stance(text)
        assert result < -0.3

    def test_estimate_stance_neutral(self):
        """Neutral text should give stance close to 0."""
        text = "The weather is nice today."
        result = estimate_stance(text)
        assert abs(result) < 0.3

    def test_stance_shift_no_change(self):
        """No stance change should give zero shift."""
        history = [0.5, 0.5, 0.5]
        result = compute_stance_shift(history)
        assert result == 0

    def test_stance_shift_leftward(self):
        """Shift toward opposition should be negative."""
        history = [0.8, 0.5, 0.2]
        result = compute_stance_shift(history)
        assert result < -0.2

    def test_stance_shift_rightward(self):
        """Shift toward support should be positive."""
        history = [0.2, 0.5, 0.8]
        result = compute_stance_shift(history)
        assert result > 0.2

    def test_consensus_alignment_unanimous(self):
        """Same stance as all should give high alignment."""
        agent_stance = 0.5
        all_stances = [0.5, 0.5, 0.5]
        result = compute_consensus_alignment(agent_stance, all_stances)
        assert result > 0.9

    def test_consensus_alignment_isolated(self):
        """Different stance from all should give low alignment."""
        agent_stance = 1.0
        all_stances = [-1.0, -1.0, -1.0]
        result = compute_consensus_alignment(agent_stance, all_stances)
        assert result < 0.3


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestMetricIntegration:
    """Integration tests for metric interactions."""

    def test_all_metrics_handle_empty_agents(self):
        """All metrics should handle empty agent list gracefully."""
        empty_agents = {}
        empty_interactions = {}

        # Should not raise exceptions
        assert isinstance(compute_betweenness_centrality(empty_agents, empty_interactions), dict)
        assert isinstance(compute_participation_balance(empty_agents), (int, float))
        assert isinstance(compute_emotion_diversity({}), (int, float))
        assert isinstance(compute_arousal_variance([]), (int, float))
        assert isinstance(compute_lexical_diversity(""), (int, float))

    def test_metric_ranges(self):
        """Metrics should return values in expected ranges."""
        # Emotion diversity: 0 to ln(num_emotions)
        diversity = compute_emotion_diversity({"joy": 1, "anger": 1})
        assert 0 <= diversity <= 2.0

        # Stance: -1 to 1
        stance = estimate_stance("I agree completely!")
        assert -1 <= stance <= 1

        # Brokerage score: 0 to infinity (but typically 0-1)
        score = compute_brokerage_score(
            {"id": "a", "cluster": "c1"},
            {"a": {}},
            {"c1": {}}
        )
        assert score >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
