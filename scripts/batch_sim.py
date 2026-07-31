#!/usr/bin/env python3
"""Batch simulation runner — calls local server to run presets, saves results."""

import sys, os, time, json
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("pip install requests"); sys.exit(1)

BASE   = "http://localhost:8002"
API    = os.environ.get("OLLAMA_URL", "https://api.ollama.com")
KEY    = os.environ.get("OLLAMA_KEY", "ec441f1d4da040dca94986deabdc4a6f.3rs7WGnx0WrXU98_kajZSnen")

PRESETS = ["ai_regulation_debate", "climate_summit", "corporate_decision", "energy_transition"]
MODELS  = ["kimi-k2.7-code", "minimax-m2.5", "qwen3.5:397b", "kimi-k2.6"]
ROUNDS  = 10
TEMP    = 0.8
OUT_DIR = Path(__file__).resolve().parent.parent / "sim"
TIMEOUT = 1200

def _post(path, data=None):
    r = requests.post(f"{BASE}{path}", json=data or {}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def _get(path):
    r = requests.get(f"{BASE}{path}", timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def _save(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, default=str)

def simulate(preset, model, folder):
    print(f"\n{'='*60}\n  {preset}  x  {model}  ({ROUNDS} rounds)\n{'='*60}")
    folder.mkdir(parents=True, exist_ok=True)

    _post("/api/reset")
    _post("/api/config", {"url": API, "key": KEY, "model": model, "temperature": TEMP})

    r = _post("/api/preset/load", {"preset_id": preset})
    if r.get("error"):
        print(f"  ERROR: {r['error']}")
        return None
    agents = r.get("agents", 0)
    print(f"  {agents} agents loaded")

    time.sleep(1)

    t0 = time.time()
    try:
        sim = _post("/api/simulate/multi-round", {"rounds": ROUNDS})
    except Exception as e:
        print(f"  SIM ERROR: {e}")
        return None
    elapsed = time.time() - t0
    done = len(sim.get("rounds", []))
    errs = [x for x in sim.get("rounds", []) if x.get("error")]
    print(f"  {done} rounds in {elapsed:.0f}s  ({len(errs)} errors)")

    state = _get("/api/state")
    for fname, ep in [
        ("problem.json",          "/api/problem/export"),
        ("results.json",          "/api/results/export"),
        ("analytics.json",        "/api/analytics/export"),
        ("conversation_log.json", "/api/log/export"),
    ]:
        try:
            data = _get(ep)
            _save(folder / fname, data)
            print(f"  saved {fname}")
        except Exception as e:
            print(f"  {fname} FAILED: {e}")

    _save(folder / "metadata.json", {
        "preset": preset, "model": model, "rounds": ROUNDS,
        "temperature": TEMP, "agents": agents,
        "rounds_completed": done, "errors": len(errs),
        "messages": state.get("total_messages", 0),
        "snapshots": state.get("total_snapshots", 0),
        "elapsed_seconds": round(elapsed, 1),
        "timestamp": datetime.utcnow().isoformat(),
    })
    return {"done": done, "time": elapsed}

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _get("/api/state")
    except:
        print(f"Server at {BASE} not reachable"); return 1

    total = len(PRESETS) * len(MODELS)
    ok, fail = 0, 0
    t_all = time.time()

    for preset in PRESETS:
        for model in MODELS:
            slug = f"sim_{preset.replace('_','-')}_{model.replace(':','-').replace('/','-')}"
            d = OUT_DIR / slug
            if d.exists():
                print(f"  SKIP {slug} (exists)")
                continue
            meta = simulate(preset, model, d)
            if meta:
                ok += 1
            else:
                fail += 1
            print(f"  [{ok+fail}/{total}] {time.time()-t_all:.0f}s")

    print(f"\nDONE  ok={ok}  fail={fail}  {time.time()-t_all:.0f}s\n{OUT_DIR}")

if __name__ == "__main__":
    main()