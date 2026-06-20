"""
SERVER INTEGRATION PATCH
========================

This file shows the exact code changes needed to integrate metrics into main.py.

Apply these changes to src/server/main.py at the specified locations.
"""

# ═══════════════════════════════════════════════════════════════════════════
# STEP 1: Add at TOP of main.py (after existing imports)
# ═══════════════════════════════════════════════════════════════════════════

"""
Add this import after line 25 (after existing imports):

from analytics.metrics_engine import engine as metrics_engine
"""


# ═══════════════════════════════════════════════════════════════════════════
# STEP 2: Update agent creation function
# ═══════════════════════════════════════════════════════════════════════════

"""
Find the agent creation function (usually fresha() or create_agent()) and add
these new fields to the agent dictionary initialization:

def create_agent(agent_id, name, cluster, role=""):
    agent = {
        # ... existing fields ...
        "id": agent_id,
        "name": name,
        "cluster": cluster,
        "role": role,
        "turncount": 0,
        "messagehistory": [],
        "valence": 0,
        "arousal": 0,
        "dominance": 0,
        "detected_emotions": {},
        "detected_files": {},
        "interactions": {},
        "mentions": {},

        # NEW FIELDS for metrics tracking
        "emotionhistory": [],      # Track emotions over time
        "arousalhistory": [],      # Track arousal values
        "stancehistory": [],       # Track stance (debate mode)
        "latencysamples": [],      # Track latency values

        # NEW METRICS - Will be computed
        "betweennessproxy": 0.0,
        "brokeragescore": 0.0,
        "emotiondiversity": 0.0,
        "dominantemotion": None,
        "arousalvariance": 0.0,
        "emotioncontagionslope": 0.0,
        "costperturn": 0.0,
        "latencyvariance": 0.0,
        "promptcompletionratio": 1.0,
        "speechacts": {},
        "lexicaldiversity": 0.0,
        "taskphasecounts": {},
        "crossfilecoordination": 0,
        "stance": 0.0,
        "stanceshift": 0.0,
        "consensusalignment": 0.0,
    }
    return agent
"""


# ═══════════════════════════════════════════════════════════════════════════
# STEP 3: Update agent after each message (in upd() or similar function)
# ═══════════════════════════════════════════════════════════════════════════

"""
In the function that updates agents after messages, add this code after
emotion detection and before returning:

def update_agent_after_message(agent_id, message_text, latency_ms, tokens_used):
    '''Update agent metrics after processing a message.'''
    agent = agents[agent_id]

    # Update basic fields
    agent["turncount"] += 1
    agent["messagehistory"].append(message_text)
    agent["latencysamples"].append(latency_ms)

    # Keep history bounded
    if len(agent["messagehistory"]) > 100:
        agent["messagehistory"] = agent["messagehistory"][-100:]
    if len(agent["latencysamples"]) > 50:
        agent["latencysamples"] = agent["latencysamples"][-50:]

    # Add to arousal history (emotion detection should have set arousal by now)
    agent["arousalhistory"].append(agent.get("arousal", 0))
    if len(agent["arousalhistory"]) > 50:
        agent["arousalhistory"] = agent["arousalhistory"][-50:]

    # For debate mode, track stance
    if MODE == "debate":
        from metrics.debate import estimate_stance
        stance = estimate_stance(message_text)
        agent["stancehistory"].append(stance)
        if len(agent["stancehistory"]) > 50:
            agent["stancehistory"] = agent["stancehistory"][-50:]

    # CRITICAL: Compute all new metrics
    metrics_engine.compute_agent_metrics(
        agent,
        list(agents.values()),
        build_interaction_graph(),  # Build from agents' interaction data
        list(CLUSTER_CONFIG.values()),
        MODE
    )

    return agent

# Helper function to build interaction graph from agents
def build_interaction_graph():
    '''Build interaction graph from agents.'''
    graph = {}
    for aid, agent in agents.items():
        graph[aid] = agent.get("interactions", {})
    return graph
"""


# ═══════════════════════════════════════════════════════════════════════════
# STEP 4: Compute global metrics after each round
# ═══════════════════════════════════════════════════════════════════════════

"""
After each simulation round completes, add this code:

def finalize_round(round_num):
    '''Finalize round and compute global metrics.'''
    # Compute global metrics
    global_metrics = metrics_engine.compute_global_metrics(
        list(agents.values()),
        list(CLUSTER_CONFIG.values()),
        MODE
    )

    # Store for later export
    round_metadata[round_num] = {
        "global_metrics": global_metrics,
        "timestamp": datetime.utcnow().isoformat(),
    }

    return global_metrics
"""


# ═══════════════════════════════════════════════════════════════════════════
# STEP 5: Update snapshot capture to include new metrics
# ═══════════════════════════════════════════════════════════════════════════

"""
In the take_snapshot() or similar function, update the agent snapshot section:

def take_snapshot(round_num, msg_index):
    '''Capture full state including all new metrics.'''
    snap = {
        "round": round_num,
        "msg_index": msg_index,
        "ts": datetime.utcnow().isoformat(),
        "agents": {},
        "cluster_config": copy_cluster_config(),
        "emotions_active": dict(_global_emotions),
        "files_active": dict(_global_files),
    }

    for aid, agent in agents.items():
        snap["agents"][aid] = {
            # Existing fields
            "id": agent["id"],
            "name": agent["name"],
            "cluster": agent["cluster"],
            "role": agent.get("role", ""),
            "valence": agent.get("valence", 0),
            "arousal": agent.get("arousal", 0),
            "dominance": agent.get("dominance", 0),
            "influence": agent.get("influence", 1),
            "turncount": agent.get("turncount", 0),
            "word_count": agent.get("word_count", 0),
            "total_tokens": agent.get("total_tokens", 0),
            "prompt_tokens": agent.get("prompt_tokens", 0),
            "completion_tokens": agent.get("completion_tokens", 0),
            "total_cost_usd": agent.get("total_cost_usd", 0),
            "avg_latency_ms": agent.get("avg_latency_ms", 0),
            "interactions": dict(agent.get("interactions", {})),
            "mentions": dict(agent.get("mentions", {})),
            "detected_emotions": dict(agent.get("detected_emotions", {})),
            "detected_files": dict(agent.get("detected_files", {})),

            # NEW FIELDS - Include all new metrics
            "betweennessproxy": agent.get("betweennessproxy", 0),
            "brokeragescore": agent.get("brokeragescore", 0),
            "emotiondiversity": agent.get("emotiondiversity", 0),
            "dominantemotion": agent.get("dominantemotion"),
            "arousalvariance": agent.get("arousalvariance", 0),
            "emotioncontagionslope": agent.get("emotioncontagionslope", 0),
            "costperturn": agent.get("costperturn", 0),
            "latencyvariance": agent.get("latencyvariance", 0),
            "promptcompletionratio": agent.get("promptcompletionratio", 1.0),
            "speechacts": agent.get("speechacts", {}),
            "lexicaldiversity": agent.get("lexicaldiversity", 0),
            "taskphasecounts": agent.get("taskphasecounts", {}),
            "crossfilecoordination": agent.get("crossfilecoordination", 0),
            "stance": agent.get("stance", 0),
            "stanceshift": agent.get("stanceshift", 0),
            "consensusalignment": agent.get("consensusalignment", 0),
        }

    # Add global metrics
    snap["globalmetrics"] = metrics_engine.compute_global_metrics(
        list(agents.values()),
        list(CLUSTER_CONFIG.values()),
        MODE
    )

    snapshots.append(snap)
    return snap
"""


# ═══════════════════════════════════════════════════════════════════════════
# STEP 6: Update analytics export
# ═══════════════════════════════════════════════════════════════════════════

"""
In the buildanalytics() or similar function, update the per-agent section:

def build_analytics():
    '''Build complete analytics export.'''
    analytics = {
        "timestamp": datetime.utcnow().isoformat(),
        "mode": MODE,
        "agents": {},
        "clusters": {},
        "global_metrics": {},
        "timeline": snapshots,
    }

    for aid, agent in agents.items():
        analytics["agents"][aid] = {
            "id": agent["id"],
            "name": agent["name"],
            "cluster": agent["cluster"],

            # Social metrics
            "social": {
                "influence": agent.get("influence", 0),
                "betweenness": agent.get("betweennessproxy", 0),
                "brokerage": agent.get("brokeragescore", 0),
                "turncount": agent.get("turncount", 0),
                "connections": len(agent.get("interactions", {})),
                "mentions": sum(agent.get("mentions", {}).values()),
            },

            # Affective metrics
            "affective": {
                "valence": agent.get("valence", 0),
                "arousal": agent.get("arousal", 0),
                "dominance": agent.get("dominance", 0),
                "emotion_diversity": agent.get("emotiondiversity", 0),
                "arousal_variance": agent.get("arousalvariance", 0),
                "dominant_emotion": agent.get("dominantemotion"),
                "contagion": agent.get("emotioncontagionslope", 0),
                "detected_emotions": agent.get("detected_emotions", {}),
            },

            # Operational metrics
            "operational": {
                "total_tokens": agent.get("total_tokens", 0),
                "prompt_tokens": agent.get("prompt_tokens", 0),
                "completion_tokens": agent.get("completion_tokens", 0),
                "cost_usd": agent.get("total_cost_usd", 0),
                "cost_per_turn": agent.get("costperturn", 0),
                "latency_ms": agent.get("avg_latency_ms", 0),
                "latency_variance": agent.get("latencyvariance", 0),
                "p_c_ratio": agent.get("promptcompletionratio", 1.0),
            },

            # Conversation metrics
            "conversation": {
                "turncount": agent.get("turncount", 0),
                "wordcount": agent.get("word_count", 0),
                "speech_acts": agent.get("speechacts", {}),
                "lexical_diversity": agent.get("lexicaldiversity", 0),
            },

            # Developer metrics
            "developer": {
                "files_detected": len(agent.get("detected_files", {})),
                "task_phases": agent.get("taskphasecounts", {}),
                "cross_file": agent.get("crossfilecoordination", 0),
            },

            # Debate metrics
            "debate": {
                "stance": agent.get("stance", 0),
                "stance_shift": agent.get("stanceshift", 0),
                "consensus_alignment": agent.get("consensusalignment", 0),
            },
        }

    # Add global metrics
    if snapshots:
        analytics["global_metrics"] = snapshots[-1].get("globalmetrics", {})

    return analytics
"""


# ═══════════════════════════════════════════════════════════════════════════
# SUMMARY OF CHANGES
# ═══════════════════════════════════════════════════════════════════════════

"""
CHECKLIST OF CODE CHANGES NEEDED:

1. ✅ Add import: metrics_engine (line ~25)
2. ✅ Add 16 new agent fields in creation function
3. ✅ Call metrics_engine.compute_agent_metrics() after each message
4. ✅ Keep arousal/stances history capped at ~50 items
5. ✅ Call metrics_engine.compute_global_metrics() after each round
6. ✅ Add new metric fields to snapshot capture
7. ✅ Add globalmetrics to snapshot
8. ✅ Update analytics export with new metric sections

TESTING AFTER INTEGRATION:

1. Create agent: verify new fields initialized to defaults
2. Process message: verify metrics computed (non-zero)
3. Take snapshot: verify new fields in JSON
4. Export results: verify analytics structure correct
5. Load old snapshot: verify backward compatibility (safe defaults)
"""
