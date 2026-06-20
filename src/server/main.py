# Social Agents City 3D - FastAPI Backend Server
# Real-time agent conversation simulation with 3D spatial visualization
import os, json, re, asyncio, time, math, shutil, traceback, copy, csv
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import requests, urllib3
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

def get_metrics():
    class DummyMetrics:
        def compute_agent_metrics(self, *args, **kwargs):
            return args[0]
        def reset_metrics(self):
            pass
    return DummyMetrics()

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PORT = 8002
CFG = {
    "url":   os.getenv("OLLAMA_URL", "https://api.ollama.com"),
    "key":   os.getenv("OLLAMA_KEY", ""),
    "ssl":   False,  # CRITICAL: Always False - ignore SSL verification errors
    "model": os.getenv("OLLAMA_MODEL", ""),
    "sentiment_model": "lexicon",
    "context_window": 60,
    "agent_history":  20,
    "mode":  "conversation",
    "temperature": 0.7,
    # Simulation context settings
    "context_turns": 5,          # Number of recent turns to include in prompt
    "include_topic": True,       # Always include topic/theme in prompt
    "include_history": True,     # Include conversation history
    "include_agent_name": True,  # Include "You are X" instruction
}

EXECUTOR = ThreadPoolExecutor(max_workers=16)
WORKSPACE = Path(os.getenv("AGENT_WORKSPACE", "./agent_workspace"))

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1: METRICS ENGINE INITIALIZATION
# ══════════════════════════════════════════════════════════════════════════════
# TODO: Fix metrics engine module imports - temporarily disabled
# _metrics_config_path = Path(__file__).parent.parent.parent / "config" / "metrics_config.json"
# initialize_metrics(str(_metrics_config_path))
# print(f"✓ Metrics engine initialized with config from {_metrics_config_path}")

# -- Dynamic cluster config (empty on boot)
CLUSTER_CONFIG = {}

# -- Shared conversation context
global_messages = []
current_round = 0

# -- Agent storage (empty on boot)
agents = {}
sim_log = []

# ══════════════════════════════════════════════════════════════════════════════
# DISTRICT SYSTEM: Multi-district parallel conversations
# ══════════════════════════════════════════════════════════════════════════════
DISTRICT_CONFIG = {}  # {district_id: {label, offset_x, offset_z, color_theme}}
district_messages = {}  # {district_id: [messages]} - messages local to each district
cross_district_messages = []  # Messages that span districts (cross-district references)
agent_district_map = {}  # {agent_id: district_id} - quick agent to district lookup

# ══════════════════════════════════════════════════════════════════════════════
# SNAPSHOT SYSTEM: captures full state at each message for timeline scrubbing
# ══════════════════════════════════════════════════════════════════════════════
snapshots = []  # ordered list of {round, msg_index, ts, agents_snapshot, cluster_config, emotions_detected, files_detected}

def _take_snapshot(round_num, msg_index, agent_id, text=""):
    """Capture a deep copy of all agent states + detected emotions/files + METRICS."""
    snap = {
        "round": round_num,
        "msg_index": msg_index,
        "ts": datetime.utcnow().isoformat(),
        "trigger_agent": agent_id,
        "agents": {},
        "cluster_config": {k: dict(v) for k, v in CLUSTER_CONFIG.items()},
        "emotions_active": dict(_global_emotions),
        "files_active": dict(_global_files),
    }
    for aid, a in agents.items():
        snap["agents"][aid] = {
            "id": a["id"], "name": a["name"], "role": a["role"],
            "cluster": a["cluster"],
            "valence": a.get("valence", 0), "arousal": a.get("arousal", 0),
            "dominance": a.get("dominance", 0), "influence": a.get("influence", 1),
            "turn_count": a.get("turn_count", 0), "word_count": a.get("word_count", 0),
            "sentence_count": a.get("sentence_count", 0),
            "total_tokens": a.get("total_tokens", 0),
            "prompt_tokens": a.get("prompt_tokens", 0),
            "completion_tokens": a.get("completion_tokens", 0),
            "total_cost_usd": a.get("total_cost_usd", 0),
            "avg_latency_ms": a.get("avg_latency_ms", 0),
            "interactions": dict(a.get("interactions", {})),
            "mentions": dict(a.get("mentions", {})),
            "allegation_count": a.get("allegation_count", 0),
            "argument_score": a.get("argument_score", 0),
            # Per-agent detected emotions and files
            "detected_emotions": dict(a.get("detected_emotions", {})),
            "detected_files": dict(a.get("detected_files", {})),
            # === PHASE 1: METRICS FIELDS ===
            "betweennessproxy": a.get("betweennessproxy", 0),
            "brokeragescore": a.get("brokeragescore", 0),
            "emotiondiversity": a.get("emotiondiversity", 0),
            "dominantemotion": a.get("dominantemotion", 0),
            "arousalvariance": a.get("arousalvariance", 0),
            "emotioncontagionslope": a.get("emotioncontagionslope", 0),
            "costperturn": a.get("costperturn", 0),
            "latencyvariance": a.get("latencyvariance", 0),
            "promptcompletionratio": a.get("promptcompletionratio", 0),
            "speechacts": a.get("speechacts", {}),
            "lexicaldiversity": a.get("lexicaldiversity", 0),
            "taskphasecounts": a.get("taskphasecounts", {}),
            "crossfilecoordination": a.get("crossfilecoordination", 0),
            "stance": a.get("stance", 0),
            "stanceshift": a.get("stanceshift", 0),
            "consensusalignment": a.get("consensusalignment", 0),
        }

    # === PHASE 1: ADD GLOBAL METRICS ===
    try:
        metrics = get_metrics()
        snap["globalmetrics"] = metrics.compute_global_metrics(
            list(agents.values()),
            list(CLUSTER_CONFIG.values()),
            mode=CFG.get("mode", "conversation")
        )
    except Exception as e:
        snap["globalmetrics"] = {"error": str(e)}

    snapshots.append(snap)
    return snap

# ══════════════════════════════════════════════════════════════════════════════
# EMOTION DETECTION: granular emotions from text -> new buildings
# ══════════════════════════════════════════════════════════════════════════════
EMOTION_KEYWORDS = {
    "joy":          ["happy","joy","joyful","cheerful","delight","pleased","glad","elated","euphoric","ecstatic","bliss","wonderful","excellent","fantastic","awesome","great"],
    "sadness":      ["sad","sadness","grief","sorrow","melancholy","miserable","unhappy","depressed","gloomy","heartbroken","disappointed","despair","down","low"],
    "anger":        ["angry","anger","furious","rage","outrage","hostile","irritated","annoyed","mad","livid","enraged","upset","furious","incensed"],
    "fear":         ["fear","afraid","scared","terrified","anxious","nervous","worried","dread","panic","alarmed","frightened","concerned","uneasy"],
    "surprise":     ["surprise","surprised","astonished","amazed","shocked","startled","unexpected","stunned","speechless","unexpected","bewildered"],
    "disgust":      ["disgust","disgusted","revolted","repulsed","appalled","sickened","nauseated","loathing","repugnant","abhorrent"],
    "trust":        ["trust","believe","faith","reliable","confident","dependable","loyal","faithful","credible","secure","assured"],
    "anticipation": ["anticipate","expect","hope","eager","look forward","excited about","planning","preparing","awaiting","upcoming"],
    "pride":        ["proud","pride","accomplished","achievement","triumphant","satisfaction","fulfilled","success","victory","triumph"],
    "shame":        ["shame","ashamed","embarrassed","humiliated","guilt","guilty","mortified","remorse","regret","disgraced"],
    "contempt":     ["contempt","disdain","scorn","dismissive","condescending","patronizing","derisive","arrogant","superior"],
    "frustration":  ["frustrated","frustration","stuck","blocked","stalled","impediment","obstacle","hindered","exasperated"],
    "curiosity":    ["curious","curiosity","wonder","intrigued","fascinated","interested","inquisitive","puzzled","questioning"],
    "gratitude":    ["grateful","thankful","appreciate","gratitude","thanks","indebted","obliged","appreciation","recognition"],
    "empathy":      ["empathy","understand","sympathize","compassion","relate to","feel for","solidarity","support","care"],
    "enthusiasm":   ["enthusiastic","enthusiasm","passionate","excited","energized","motivated","thrilled","pumped","vibrant"],
    "skepticism":   ["skeptical","doubt","dubious","questionable","unconvinced","suspicious","wary","uncertain","disbelief"],
    "hope":         ["hope","hopeful","optimistic","promising","bright future","aspire","dream","envision","optimism"],
    "resignation":  ["resigned","accept","inevitable","give up","surrender","concede","yield","acquiesce","acceptance"],
    "determination":["determined","resolute","committed","dedicated","persistent","tenacious","unwavering","resolve","drive"],
    "confidence":   ["confident","confidence","certain","sure","assured","secure","self-assured","poised"],
    "confusion":    ["confused","confusion","uncertain","unclear","puzzled","perplexed","bewildered","lost","disoriented"],
}

_global_emotions = {}  # emotion_name -> {count, first_round, agents: set}
_global_files = {}     # filename -> {agent_id, round, language, lines_approx}

def detect_emotions(text):
    """Detect granular emotions from text using lexicon, return dict of emotion->intensity."""
    words = re.findall(r"[a-z']+", text.lower())
    detected = {}

    # Use lexicon if available, otherwise fall back to keywords
    if EMOTION_LEXICON:
        # Count emotions from lexicon
        emotion_counts = {}
        for w in words:
            if w in EMOTION_LEXICON:
                entry = EMOTION_LEXICON[w]
                emo = entry.get('emotion')
                if emo:
                    emotion_counts[emo] = emotion_counts.get(emo, 0) + 1

        # Normalize to 0-1 intensity
        if emotion_counts:
            max_count = max(emotion_counts.values())
            for emo, count in emotion_counts.items():
                detected[emo] = min(count / max(max_count, 1) * 1.0, 1.0)
    else:
        # Fallback to keyword-based detection
        for emotion, keywords in EMOTION_KEYWORDS.items():
            count = sum(1 for w in words if w in keywords)
            # Also check multi-word patterns
            lower_text = text.lower()
            for kw in keywords:
                if ' ' in kw and kw in lower_text:
                    count += 1
            if count > 0:
                detected[emotion] = min(count / max(len(words), 1) * 10, 1.0)

    return detected

def detect_code_files(text):
    """Detect file references in developer mode text."""
    files = {}
    # Match patterns like `filename.ext`, filename.py, etc.
    file_patterns = re.findall(r'`?([a-zA-Z_][\w.-]*\.(py|js|ts|jsx|tsx|go|rs|java|cpp|c|h|html|css|sql|yaml|yml|json|toml|md|sh|rb|php|swift|kt))`?', text)
    for fname, ext in file_patterns:
        lang_map = {"py":"Python","js":"JavaScript","ts":"TypeScript","jsx":"React","tsx":"React+TS",
                    "go":"Go","rs":"Rust","java":"Java","cpp":"C++","c":"C","h":"C/C++ Header",
                    "html":"HTML","css":"CSS","sql":"SQL","yaml":"YAML","yml":"YAML","json":"JSON",
                    "toml":"TOML","md":"Markdown","sh":"Shell","rb":"Ruby","php":"PHP",
                    "swift":"Swift","kt":"Kotlin"}
        files[fname] = {"language": lang_map.get(ext, ext), "extension": ext}
    # Count approximate code lines (lines inside code blocks)
    code_blocks = re.findall(r'```[\w]*\n(.*?)```', text, re.DOTALL)
    total_lines = sum(len(block.strip().split('\n')) for block in code_blocks)
    for f in files:
        files[f]["lines_approx"] = total_lines // max(len(files), 1)
    return files


# ══════════════════════════════════════════════════════════════════════════════
# SOFTWARE DEVELOPMENT MODE: Git repository analysis (future implementation)
# ══════════════════════════════════════════════════════════════════════════════

def clone_git_repo(url, workspace_path):
    """Clone repository for analysis (future implementation)."""
    # TODO: Implement when software development mode is activated
    # - Use git clone to download repository
    # - Store at workspace_path for agent analysis
    pass

def analyze_git_changes(agent_id, commit_hash):
    """Analyze what an agent changed in codebase (future implementation)."""
    # TODO: Analyze:
    # - Files modified in commit
    # - Lines added/removed per file
    # - Code complexity metrics
    # - Test coverage impact
    pass

def detect_coding_patterns(text):
    """Detect coding discussions and decisions (future implementation)."""
    # TODO: Detect patterns like:
    # - "implemented", "refactored", "fixed bug", "deployed"
    # - Architecture mentions and decisions
    # - Design patterns discussed
    # - Technical debt acknowledgment
    pass


def _emotion_summary(emotions):
    """Generate textual summary of predominant emotions."""
    if not emotions:
        return "Neutral"
    sorted_emos = sorted(emotions.items(), key=lambda x: x[1], reverse=True)
    top_3 = sorted_emos[:3]
    return ", ".join([e.capitalize() for e, _ in top_3])


def analyze_emotions_detailed(text, agent_id):
    """Detailed emotion analysis with change tracking."""
    detected = detect_emotions(text)
    new_emotions = []
    intensified = []

    # Compare with previous emotions if agent exists
    if agent_id in agents:
        prev_emos = agents[agent_id].get("detected_emotions", {})
        # New emotions detected
        new_emotions = [e for e in detected if e not in prev_emos]
        # Intensified emotions
        intensified = [e for e, v in detected.items()
                      if e in prev_emos and v > prev_emos[e].get("total_intensity", 0)]

    return {
        "detected": detected,
        "new": new_emotions,
        "intensified": intensified,
        "summary": _emotion_summary(detected)
    }


# -- PAD Sentiment Lexicon
POS_VALENCE = set("great good excellent happy agree wonderful positive love fantastic hope "
                  "brilliant success benefit support innovative efficient solution improve "
                  "promising opportunity thrive collaborative inclusive fair sustainable "
                  "outstanding inspire achievement proud joy cheerful delight pleasure".split())
NEG_VALENCE = set("bad poor disagree wrong terrible negative fail risk problem cost "
                  "dangerous harmful oppose worry crisis concern inefficient waste "
                  "inequality unaffordable injustice conflict tension divide polarize "
                  "awful dreadful miserable frustrate anger fear sadness grief regret".split())
HIGH_AROUSAL = set("urgent exciting energetic intense critical immediate powerful dynamic "
                   "explosive revolutionary drastic radical must should never always "
                   "breakthrough incredible phenomenal extraordinary".split())
LOW_AROUSAL  = set("calm gentle slow steady quiet moderate gradual mild subtle "
                   "balanced nuanced reflective careful considered thoughtful".split())
HIGH_DOM = set("should must will demand require insist command lead control "
               "decide determine force establish mandate".split())
LOW_DOM  = set("maybe perhaps might could possibly suggest wonder ask request "
               "hope wish consider allow permit enable".split())

# ══════════════════════════════════════════════════════════════════════════════
# TEXT-ANALYSIS-MASTER: Emotion Lexicon (14,852 words)
# ══════════════════════════════════════════════════════════════════════════════

import csv
from pathlib import Path

# Cargar lexicon compilado al inicio
LEXICON_PATH = Path(__file__).parent.parent.parent / "data" / "lexicons" / "emotions_compiled.csv"
EMOTION_LEXICON = {}  # {word: {emotion, color, sentiment, subjectivity}}

def load_emotion_lexicon():
    """Carga el lexicon compilado de text-analysis-master en memoria."""
    global EMOTION_LEXICON
    if LEXICON_PATH.exists():
        try:
            with open(LEXICON_PATH, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    word = row['word'].lower()
                    EMOTION_LEXICON[word] = {
                        'emotion': row['emotion'] if row['emotion'] else None,
                        'color': row['color'] if row['color'] else None,
                        'sentiment': row['sentiment'] if row['sentiment'] else None,
                        'subjectivity': row['subjectivity'] if row['subjectivity'] else None,
                        'source': row['source']
                    }
            print(f"[INFO] Loaded {len(EMOTION_LEXICON)} words from emotion lexicon")
        except Exception as e:
            print(f"[WARNING] Could not load emotion lexicon: {e}")
    else:
        print(f"[WARNING] Lexicon not found at {LEXICON_PATH}")

# Cargar al importar el módulo
load_emotion_lexicon()

# Mapeo de emociones a colores hex (para frontend)
EMOTION_COLORS_HEX = {
    'joy': '#fbbf24',           # amarillo
    'anger': '#ef4444',         # rojo
    'fear': '#8b5cf6',          # morado
    'sadness': '#3b82f6',       # azul
    'disgust': '#84cc16',       # verde lima
    'surprise': '#f97316',      # naranja
    'trust': '#22c55e',         # verde
    'anticipation': '#06b6d4',  # cyan
}

def get_word_emotion(word):
    """Retorna información emocional de una palabra desde el lexicon."""
    w = word.lower().strip(".,;:!?()[]{}\"'")
    entry = EMOTION_LEXICON.get(w)
    if entry and entry['emotion']:
        return {
            'word': word,
            'emotion': entry['emotion'],
            'color': EMOTION_COLORS_HEX.get(entry['emotion'], '#8b949e'),
            'sentiment': entry['sentiment'],
            'lexicon_color': entry['color']  # Color del lexicon original
        }
    return None

def _lexicon_pad(text):
    words = re.findall(r"[a-z']+", text.lower())
    n = max(len(words), 1)
    v = sum(1 for w in words if w in POS_VALENCE) - sum(1 for w in words if w in NEG_VALENCE)
    a = sum(1 for w in words if w in HIGH_AROUSAL) - sum(1 for w in words if w in LOW_AROUSAL)
    d = sum(1 for w in words if w in HIGH_DOM) - sum(1 for w in words if w in LOW_DOM)
    return round(v/n, 3), round(a/n, 3), round(d/n, 3)

def _llm_pad(text, model):
    try:
        msgs = [{"role":"system","content":"Analyze sentiment. Return JSON: {\"valence\":float(-1,1),\"arousal\":float(-1,1),\"dominance\":float(-1,1)}"},
                {"role":"user","content":text[:500]}]
        reply, _ = ollama_chat(model, msgs, 0.1)
        m = re.search(r'\{[^}]+\}', reply)
        if m:
            d = json.loads(m.group())
            return (round(float(d.get("valence",0)),3),
                    round(float(d.get("arousal",0)),3),
                    round(float(d.get("dominance",0)),3))
    except:
        pass
    return _lexicon_pad(text)

def pad_sentiment(text):
    sm = CFG.get("sentiment_model","lexicon")
    if sm == "lexicon" or not sm:
        return _lexicon_pad(text)
    return _llm_pad(text, sm)

# ══════════════════════════════════════════════════════════════════════════════
# TEXT-ANALYSIS-MASTER: Emotion Lexicon (14,852 words)
# ══════════════════════════════════════════════════════════════════════════════

LEXICON_PATH = Path(__file__).parent.parent.parent / "data" / "lexicons" / "emotions_compiled.csv"
EMOTION_LEXICON = {}  # {word: {emotion, color, sentiment, subjectivity, source}}

def load_emotion_lexicon():
    """Carga el lexicon compilado de text-analysis-master en memoria."""
    global EMOTION_LEXICON
    if LEXICON_PATH.exists():
        try:
            with open(LEXICON_PATH, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                count = 0
                for row in reader:
                    word = row['word'].lower().strip()
                    if word:
                        EMOTION_LEXICON[word] = {
                            'emotion': row.get('emotion', '').strip() or None,
                            'color': row.get('color', '').strip() or None,
                            'sentiment': row.get('sentiment', '').strip() or None,
                            'subjectivity': row.get('subjectivity', '').strip() or None,
                            'source': row.get('source', '').strip()
                        }
                        count += 1
            print(f"[EMOTION_LEXICON] Loaded {count} words from {LEXICON_PATH}")
        except Exception as e:
            print(f"[ERROR] Failed to load emotion lexicon: {e}")
    else:
        print(f"[WARNING] Lexicon not found at {LEXICON_PATH}")

# Mapeo de emociones a colores hex (para frontend)
EMOTION_COLORS_HEX = {
    'joy': '#fbbf24',           # amarillo
    'anger': '#ef4444',         # rojo
    'fear': '#8b5cf6',          # morado
    'sadness': '#3b82f6',       # azul
    'disgust': '#84cc16',       # verde lima
    'surprise': '#f97316',      # naranja
    'trust': '#22c55e',         # verde
    'anticipation': '#06b6d4',  # cyan
}

def get_word_emotion(word):
    """Retorna información emocional de una palabra desde el lexicon."""
    w = word.lower().strip(".,;:!?()[]{}\"'")
    if not w:
        return None
    entry = EMOTION_LEXICON.get(w)
    if entry and entry['emotion']:
        return {
            'word': word,
            'emotion': entry['emotion'],
            'color': EMOTION_COLORS_HEX.get(entry['emotion'], '#8b949e'),
            'sentiment': entry['sentiment'],
            'lexicon_color': entry['color']  # Color del lexicon original
        }
    return None

# Cargar lexicon al iniciar
load_emotion_lexicon()

def normalize_text(text):
    """Normaliza caracteres especiales problemáticos (p.ej. non-breaking hyphens)"""
    if not text:
        return text
    # Reemplaza non-breaking hyphen (U+2011) y otros guiones especiales con hyphen-minus
    text = text.replace('‑', '-')  # non-breaking hyphen
    text = text.replace('‐', '-')  # hyphen
    text = text.replace('‒', '-')  # figure dash
    text = text.replace('–', '-')  # en dash
    text = text.replace('—', '-')  # em dash
    text = text.replace('―', '-')  # horizontal bar
    return text

def split_sentences(text):
    text = normalize_text(text)
    # Replace common abbreviations temporarily to avoid splitting on them
    abbrevs = [r'\bDr\.',r'\bMr\.',r'\bMs\.',r'\bMrs\.',r'\bProf\.',r'\bAmb\.',r'\bRev\.',r'\bSr\.',r'\bJr\.',r'\bPh\.D\.',r'\bM\.A\.',r'\bB\.A\.']
    placeholders = {}
    for i, abbr in enumerate(abbrevs):
        placeholder = f"__ABBREV_{i}__"
        text = re.sub(abbr, placeholder, text)
        placeholders[placeholder] = abbr.replace(r'\b', '').replace(r'\.', '.')

    # Now split sentences
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])|(?<=[!?])\s+|(?<=[.!?])\s*$', text.strip())

    # Restore abbreviations
    sentences = [s.strip() for s in sentences if s.strip()]
    for i, abbr in enumerate(abbrevs):
        placeholder = f"__ABBREV_{i}__"
        sentences = [s.replace(placeholder, placeholders[placeholder]) for s in sentences]

    return sentences

def analyse_reply(text, agent_names):
    sentences = split_sentences(text)
    sent_data = []
    v_sum = a_sum = d_sum = 0.0

    # Extract top 5 keywords (4+ chars, excluding stopwords)
    words = [w.lower() for w in re.findall(r'\b\w{4,}\b', text)]
    stopwords = {'that','this','with','have','from','they','been','were','their','which','about','other','these','those','would','could','should','think','know'}
    word_freq = {}
    for w in words:
        if w not in stopwords:
            word_freq[w] = word_freq.get(w, 0) + 1
    top_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:5]

    for s in sentences:
        v, a, d = pad_sentiment(s)
        wc = len(s.split())
        mentions = [aid for name, aid in agent_names.items() if name.lower() in s.lower()]

        # Words emotions - extract words with detected emotions
        words_emotions = []
        words = re.findall(r'\b\w+\b', s)
        for word in words:
            emotion_data = get_word_emotion(word)
            if emotion_data:
                words_emotions.append({
                    "word": word,
                    "emotion": emotion_data['emotion']
                })

        sent_data.append({
            "text": s,
            "valence": v,
            "arousal": a,
            "dominance": d,
            "word_count": wc,
            "mentions": mentions,
            "words_emotions": words_emotions  # Array de palabras con emociones
        })
        v_sum += v; a_sum += a; d_sum += d
    n = max(len(sentences), 1)

    # Collect all mentions across all sentences
    all_mentions = list(dict.fromkeys([aid for s in sent_data for aid in s.get("mentions", [])]))

    return sent_data, round(v_sum/n, 3), round(a_sum/n, 3), round(d_sum/n, 3), top_words, all_mentions

def detect_mentions(text, agent_names):
    tl = text.lower()
    return [aid for name, aid in agent_names.items() if name.lower() in tl]

# -- Ollama helpers
def _h():
    h = {"Content-Type": "application/json"}
    if CFG["key"]:
        h["Authorization"] = f"Bearer {CFG['key']}"
    return h

def get_models():
    url = CFG["url"].rstrip("/")
    verify = CFG.get("ssl", True)
    for endpoint, parser, kind in [
        ("/api/tags", lambda d: [m["name"] for m in d.get("models",[])], "ollama"),
        ("/v1/models", lambda d: [m["id"] for m in d.get("data",[])], "openai"),
    ]:
        try:
            r = requests.get(f"{url}{endpoint}", headers=_h(), timeout=15, verify=verify)
            r.raise_for_status()
            models = parser(r.json())
            if models:
                return models, kind
        except:
            pass
    try:
        r = requests.get(f"{url}/api/tags", timeout=10, verify=False)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models",[])]
        if models:
            return models, "ollama"
    except:
        pass
    return [], None

def ollama_chat(model, messages, temperature=None):
    if temperature is None:
        temperature = CFG.get("temperature", 0.7)
    url = CFG["url"].rstrip("/")
    verify = CFG.get("ssl", True)
    payload = {"model": model, "messages": messages, "stream": False,
               "options": {"temperature": temperature}}
    t0 = time.time()
    try:
        r = requests.post(f"{url}/api/chat", json=payload, headers=_h(),
                          timeout=180, verify=False)  # SSL: False
        r.raise_for_status()
        d = r.json()
        content = d["message"]["content"]
        pt = d.get("prompt_eval_count", 0)
        ct = d.get("eval_count", 0)
        tt = pt + ct
        lat = round((time.time() - t0) * 1000, 1)
        cost = 0.0  # Ollama API is free
        return content, {"prompt_tokens": pt, "completion_tokens": ct,
                         "total_tokens": tt, "latency_ms": lat, "cost_usd": cost}
    except Exception as first_err:
        pass
    oai_payload = {"model": model, "messages": messages,
                   "temperature": temperature, "stream": False}
    r = requests.post(f"{url}/v1/chat/completions", json=oai_payload,
                      headers=_h(), timeout=180, verify=False)  # SSL: False
    r.raise_for_status()
    d = r.json()
    choice = d["choices"][0]
    content = choice["message"]["content"]
    usage = d.get("usage", {})
    pt = usage.get("prompt_tokens", 0)
    ct = usage.get("completion_tokens", 0)
    tt = usage.get("total_tokens", pt + ct)
    lat = round((time.time() - t0) * 1000, 1)
    cost = 0.0  # Ollama API is free
    return content, {"prompt_tokens": pt, "completion_tokens": ct,
                     "total_tokens": tt, "latency_ms": lat, "cost_usd": cost}

# -- Agent data helpers
def _fresh(a):
    return {**a, "history":[], "valence":0.0, "arousal":0.0, "dominance":0.0,
            "influence":1.0, "total_tokens":0, "prompt_tokens":0, "completion_tokens":0,
            "total_cost_usd":0.0, "avg_latency_ms":0, "turn_count":0,
            "word_count":0, "sentence_count":0, "sentences":[],
            "interactions":{}, "mentions":{}, "allegation_count":0,
            "argument_score":0, "latency_samples":[], "cost_samples":[],
            "detected_emotions":{}, "detected_files":{},
            "message_history":[],
            # NEW METRICS - SOCIAL (6 metrics for multi-channel encoding)
            "betweennessproxy":0.0, "brokeragescore":0.0, "reciprocity":0.0, "discourse_consistency":0.0,
            "closeness_centrality":0.0, "clustering_coefficient":0.0, "response_diversity":0.0, "eigenvector_centrality":0.0,
            "pagerank_proxy":0.0, "structural_holes":0.0,
            # NEW METRICS - AFFECTIVE (7 metrics for multi-channel encoding)
            "emotiondiversity":0.0, "arousalvariance":0.0, "emotioncontagion":0.0,
            "valence_volatility":0.0, "emotional_inertia":0.0, "sentiment_drift":0.0, "polarity_mismatch":0.0,
            "affective_influence":0.0, "toxicity_score":0.0,
            # NEW METRICS - OPERATIONAL (4 metrics for multi-channel encoding)
            "costperturn":0.0, "latencyvariance":0.0, "promptcompletionratio":0.0, "costvariance":0.0,
            "throughput":0.0, "context_utilization":0.0, "retry_rate":0.0, "token_efficiency":0.0,
            # NEW METRICS - COORDINATION (6 metrics for multi-channel encoding)
            "stance_intensity":0.0, "argument_strength":0.0, "consensus_alignment":0.0,
            "planning_load":0.0, "review_depth":0.0, "xref_load":0.0,
            "turn_taking_equity":0.5, "initiative_ratio":0.5, "convergence_contribution":0.0, "delegation_load":0.0,
            "valence_history":[], "arousal_history":[], "dominance_history":[]}  # History for time-series metrics

def _upd(aid, text, usage, va, ar, dom, sents, top_words=None, all_mentions=None):
    text = normalize_text(text)
    a = agents[aid]
    a["turn_count"] += 1
    a["total_tokens"] += usage["total_tokens"]
    a["prompt_tokens"] += usage["prompt_tokens"]
    a["completion_tokens"] += usage["completion_tokens"]
    a["total_cost_usd"] += usage["cost_usd"]
    a["latency_samples"].append(usage["latency_ms"])
    if len(a["latency_samples"]) > 100:
        a["latency_samples"] = a["latency_samples"][-100:]
    a["avg_latency_ms"] = round(sum(a["latency_samples"])/len(a["latency_samples"]),1)
    a["word_count"] += len(text.split())
    a["sentence_count"] += len(sents)
    a["sentences"] = (a["sentences"] + sents)[-40:]

    # === PHASE 1 FIX: Valence rolling window (last 5 messages) ===
    # Maintain valence history for better emotional sensitivity
    if "valence_history" not in a:
        a["valence_history"] = []
    if "arousal_history" not in a:
        a["arousal_history"] = []
    if "dominance_history" not in a:
        a["dominance_history"] = []

    # Add new values to history (keep last 5 messages only)
    a["valence_history"].append(va)
    a["arousal_history"].append(ar)
    a["dominance_history"].append(dom)

    if len(a["valence_history"]) > 5:
        a["valence_history"] = a["valence_history"][-5:]
    if len(a["arousal_history"]) > 5:
        a["arousal_history"] = a["arousal_history"][-5:]
    if len(a["dominance_history"]) > 5:
        a["dominance_history"] = a["dominance_history"][-5:]

    # Compute from rolling window (more reactive than full average)
    n = a["turn_count"]
    window_size = len(a["valence_history"])

    # Use rolling window average for emotional metrics (more sensitive)
    # But keep historical weight for stability
    window_avg_valence = sum(a["valence_history"]) / window_size if window_size > 0 else 0
    window_avg_arousal = sum(a["arousal_history"]) / window_size if window_size > 0 else 0
    window_avg_dominance = sum(a["dominance_history"]) / window_size if window_size > 0 else 0

    # === OPTIMIZACIÓN: Dynamic weighting para evitar "stuck" values ===
    # Más reactivo: detecta cambios incluso de 0.02 (2% change)
    # Thresholds más bajos para mayor sensibilidad emocional

    diff_v = abs(window_avg_valence - a.get("valence", 0))
    if diff_v > 0.2:       # Big emotional shift
        weight = 0.95
    elif diff_v > 0.1:     # Medium change
        weight = 0.85
    elif diff_v > 0.03:    # Small change (reduced threshold)
        weight = 0.75
    else:                  # Minimal (avoid stuck)
        weight = 0.70

    a["valence"]   = round(weight * window_avg_valence + (1-weight) * a["valence"], 3)
    a["arousal"]   = round(weight * window_avg_arousal + (1-weight) * a["arousal"], 3)
    a["dominance"] = round(weight * window_avg_dominance + (1-weight) * a["dominance"], 3)
    a["influence"]  = round(1 + a["turn_count"]*0.15 +
                            len(a["interactions"])*0.25 +
                            sum(a["mentions"].values())*0.1 +
                            a["argument_score"]*0.3, 2)
    # Detect and accumulate emotions with detailed analysis
    emo_analysis = analyze_emotions_detailed(text, aid)
    emos = emo_analysis["detected"]
    a["emotion_summary"] = emo_analysis["summary"]
    a["emotion_changes"] = {"new": emo_analysis["new"], "intensified": emo_analysis["intensified"]}

    for emo, intensity in emos.items():
        if emo not in a["detected_emotions"]:
            a["detected_emotions"][emo] = {"count": 0, "total_intensity": 0.0, "first_round": current_round}
        a["detected_emotions"][emo]["count"] += 1
        a["detected_emotions"][emo]["total_intensity"] += intensity
        # Global emotion tracking
        if emo not in _global_emotions:
            _global_emotions[emo] = {"count": 0, "first_round": current_round, "agents": []}
        _global_emotions[emo]["count"] += 1
        if aid not in _global_emotions[emo]["agents"]:
            _global_emotions[emo]["agents"].append(aid)

    # Store message in history for conversation view
    message_record = {
        "round": current_round,
        "turn": a["turn_count"],
        "text": text[:500],  # Guardar primeros 500 chars
        "tokens": usage["total_tokens"],
        "prompt_tokens": usage["prompt_tokens"],
        "completion_tokens": usage["completion_tokens"],
        "latency_ms": usage["latency_ms"],
        "valence": va,
        "arousal": ar,
        "dominance": dom,
        "word_count": len(text.split()),
        "sentence_count": len(sents),
        "emotions": emos,
        "emotion_summary": emo_analysis["summary"],
        "top_words": [{"word": w, "count": c} for w, c in (top_words or [])],
        "mentions": all_mentions or []
    }
    a["message_history"].append(message_record)
    # Mantener solo últimos 50 mensajes por agente
    if len(a["message_history"]) > 50:
        a["message_history"] = a["message_history"][-50:]

    # Detect files in developer mode
    if CFG.get("mode") == "developer":
        files = detect_code_files(text)
        for fname, fdata in files.items():
            if fname not in a["detected_files"]:
                a["detected_files"][fname] = {**fdata, "first_round": current_round, "mentions": 0}
            a["detected_files"][fname]["mentions"] += 1
            # Global file tracking
            if fname not in _global_files:
                _global_files[fname] = {**fdata, "agent_id": aid, "round": current_round, "mentions": 0}
            _global_files[fname]["mentions"] += 1

    # ═══════════════════════════════════════════════════════════════════════
    # NEW METRICS CALCULATION (v45)
    # ═══════════════════════════════════════════════════════════════════════

    # SOCIAL: Reciprocity - mutual exchange ratio
    mutual_count = sum(1 for other_id, count in a["interactions"].items()
                       if other_id in agents and a["id"] in agents[other_id].get("interactions", {}))
    total_interactions = len(a["interactions"]) if a["interactions"] else 1
    a["reciprocity"] = round(mutual_count / total_interactions, 3) if total_interactions > 0 else 0.0

    # SOCIAL: Betweenness proxy (using interaction centrality as approximation)
    all_interactions = [ag.get("interactions", {}) for ag in agents.values()]
    a["betweennessproxy"] = round(len(a["interactions"]) / max(sum(len(inter) for inter in all_interactions) / len(agents), 1), 3)

    # SOCIAL: Brokerage - cross-cluster interactions
    agent_cluster = a.get("cluster", "default")
    cross_cluster = sum(1 for other_id in a.get("interactions", {})
                       if other_id in agents and agents[other_id].get("cluster") != agent_cluster)
    a["brokeragescore"] = round(cross_cluster / total_interactions, 3) if total_interactions > 0 else 0.0

    # AFFECTIVE: Arousal variance - variability of emotional intensity
    if len(a["message_history"]) > 1:
        arousals = [msg.get("arousal", 0) for msg in a["message_history"][-20:]]
        if len(arousals) > 1:
            mean_arousal = sum(arousals) / len(arousals)
            variance = sum((x - mean_arousal) ** 2 for x in arousals) / len(arousals)
            a["arousalvariance"] = round(variance ** 0.5, 3)

    # AFFECTIVE: Emotion diversity - Shannon entropy of emotion distribution
    total_emotion_count = sum(emo.get("count", 0) for emo in a["detected_emotions"].values())
    if total_emotion_count > 0:
        entropy = 0
        for emo_data in a["detected_emotions"].values():
            p = emo_data.get("count", 0) / total_emotion_count
            if p > 0:
                entropy -= p * math.log(p)
        max_entropy = math.log(len(a["detected_emotions"])) if len(a["detected_emotions"]) > 0 else 1
        a["emotiondiversity"] = round(entropy / max(max_entropy, 1), 3)
    else:
        a["emotiondiversity"] = 0.0

    # AFFECTIVE: Emotion contagion - average alignment with group valence
    group_valence = sum(ag.get("valence", 0) for ag in agents.values()) / len(agents) if agents else 0
    a["emotioncontagion"] = round(abs(a["valence"] - group_valence), 3)

    # OPERATIONAL: Cost per turn
    a["costperturn"] = round(a["total_cost_usd"] / max(a["turn_count"], 1), 4)

    # OPERATIONAL: Latency variance
    if len(a["latency_samples"]) > 1:
        mean_latency = sum(a["latency_samples"]) / len(a["latency_samples"])
        variance = sum((x - mean_latency) ** 2 for x in a["latency_samples"]) / len(a["latency_samples"])
        a["latencyvariance"] = round(variance ** 0.5 / 1000, 3)  # Convert to seconds

    # OPERATIONAL: Cost variance
    if len(a["message_history"]) > 1:
        costs = [msg.get("latency_ms", 0) / 1000 * 0.0001 for msg in a["message_history"][-20:]]  # Rough estimate
        if len(costs) > 1:
            mean_cost = sum(costs) / len(costs)
            variance = sum((x - mean_cost) ** 2 for x in costs) / len(costs)
            a["costvariance"] = round(variance ** 0.5, 5)

    # OPERATIONAL: Prompt/Completion ratio
    a["promptcompletionratio"] = round(a["prompt_tokens"] / max(a["completion_tokens"], 1), 3)

    # COORDINATION: Stance intensity - emotional conviction (use arousal as proxy if no emotions yet)
    if total_emotion_count > 0:
        avg_emotion_intensity = sum(emo.get("total_intensity", 0) for emo in a["detected_emotions"].values()) / total_emotion_count
        a["stance_intensity"] = round(min(avg_emotion_intensity, 1), 3)
    else:
        # Use arousal as initial proxy for stance intensity
        a["stance_intensity"] = round(min(a["arousal"] or 0.0, 1), 3)

    # COORDINATION: Argument strength - word count density in messages (normalized 0-1)
    if a["turn_count"] > 0 and a["word_count"] > 0:
        avg_words_per_msg = a["word_count"] / a["turn_count"]
        a["argument_strength"] = round(min(avg_words_per_msg / 100, 1), 3)
    else:
        # Default: assume moderate argument strength
        a["argument_strength"] = 0.3

    # COORDINATION: Consensus alignment - proximity to group mean sentiment (0-1)
    if len(agents) > 0:
        group_sentiment = sum(ag.get("valence", 0) for ag in agents.values()) / len(agents)
        a["consensus_alignment"] = round(min(1 - abs(a["valence"] - group_sentiment) / 2, 1), 3)
    else:
        # Default: assume neutral/moderate alignment
        a["consensus_alignment"] = 0.5

    # COORDINATION: Planning load - file/artifact references (normalized 0-1)
    file_mentions = sum(1 for _ in a.get("detected_files", {}))
    a["planning_load"] = round(min(file_mentions * 0.2, 1), 3)

    # COORDINATION: Review depth - argument score accumulated (normalized 0-1)
    a["review_depth"] = round(min(a.get("argument_score", 0) / 10, 1), 3)

    # COORDINATION: Cross-reference load - message history references (normalized 0-1)
    xref_count = sum(1 for msg in a["message_history"] if "mentioned" in str(msg).lower())
    a["xref_load"] = round(min(xref_count / max(a["turn_count"], 1), 1), 3) if a["turn_count"] > 0 else 0.0

    # ═══════════════════════════════════════════════════════════════════════
    # NEW METRICS (Phase 1 - CodeCity Multi-Channel Framework)
    # ═══════════════════════════════════════════════════════════════════════

    # SOCIAL Bundle - Additional metrics
    # Closeness centrality (simplified: inverse mean distance in interaction graph)
    if len(a["interactions"]) > 0:
        avg_distance = sum(1.0 / max(count, 1) for count in a["interactions"].values()) / len(a["interactions"])
        a["closeness_centrality"] = round(1.0 / max(avg_distance, 0.01), 3)
    else:
        a["closeness_centrality"] = 0.0

    # Clustering coefficient (ratio of reciprocated to total interactions)
    mutual = sum(1 for partner_id in a["interactions"]
                 if partner_id in agents and a["id"] in agents[partner_id].get("interactions", {}))
    a["clustering_coefficient"] = round(mutual / max(len(a["interactions"]), 1), 3)

    # Response diversity (Shannon entropy of reply distribution)
    if len(a["interactions"]) > 0:
        total = sum(a["interactions"].values())
        probs = [count / total for count in a["interactions"].values()]
        entropy = -sum(p * math.log(p) for p in probs if p > 0)
        max_entropy = math.log(len(a["interactions"])) if len(a["interactions"]) > 1 else 1
        a["response_diversity"] = round(entropy / max(max_entropy, 0.01), 3)
    else:
        a["response_diversity"] = 0.0

    # Eigenvector centrality proxy (weighted by reciprocal connections)
    a["eigenvector_centrality"] = round(sum(1.0 / (1 + i) for i in range(len(a["interactions"]))) / max(len(agents), 1), 3)

    # PageRank proxy (simplified: betweenness + reciprocal bonus)
    a["pagerank_proxy"] = round((a.get("betweennessproxy", 0) * 0.85 + a.get("reciprocity", 0) * 0.15), 3)

    # Structural holes (simplified: inverse of clustering coefficient as brokerage opportunity)
    a["structural_holes"] = round(1.0 - a.get("clustering_coefficient", 0), 3)

    # AFFECTIVE Bundle - Additional metrics
    # Valence volatility (stdev of recent valence)
    if len(a.get("valence_history", [])) >= 2:
        valences = a.get("valence_history", [])[-10:]
        if len(valences) > 1:
            mean_val = sum(valences) / len(valences)
            variance = sum((v - mean_val) ** 2 for v in valences) / len(valences)
            a["valence_volatility"] = round(variance ** 0.5, 3)
        else:
            a["valence_volatility"] = 0.0
    else:
        a["valence_volatility"] = 0.0

    # Emotional inertia (autocorrelation of valence at lag 1)
    if len(a.get("valence_history", [])) >= 3:
        valences = a.get("valence_history", [])[-10:]
        if len(valences) >= 2:
            v_current = valences[:-1]
            v_prev = valences[1:]
            mean_current = sum(v_current) / len(v_current)
            mean_prev = sum(v_prev) / len(v_prev)
            numerator = sum((v_current[i] - mean_current) * (v_prev[i] - mean_prev) for i in range(len(v_current)))
            denominator = (sum((v - mean_current) ** 2 for v in v_current) * sum((v - mean_prev) ** 2 for v in v_prev)) ** 0.5
            a["emotional_inertia"] = round(numerator / max(denominator, 0.01), 3) if denominator > 0 else 0.0
        else:
            a["emotional_inertia"] = 0.0
    else:
        a["emotional_inertia"] = 0.0

    # Sentiment drift (slope of valence over time, approximated)
    if len(a.get("valence_history", [])) >= 2:
        valences = a.get("valence_history", [])[-10:]
        if len(valences) >= 2:
            x = list(range(len(valences)))
            mean_x = sum(x) / len(x)
            mean_v = sum(valences) / len(valences)
            slope = sum((x[i] - mean_x) * (valences[i] - mean_v) for i in range(len(x))) / max(sum((xi - mean_x) ** 2 for xi in x), 0.01)
            a["sentiment_drift"] = round(slope, 4)
        else:
            a["sentiment_drift"] = 0.0
    else:
        a["sentiment_drift"] = 0.0

    # Polarity mismatch (frequency of going against group sentiment)
    group_valence = sum(ag.get("valence", 0) for ag in agents.values()) / len(agents) if agents else 0
    mismatches = sum(1 for v in a.get("valence_history", [])[-10:] if (v > 0) != (group_valence > 0))
    a["polarity_mismatch"] = round(mismatches / max(len(a.get("valence_history", [])), 1), 3)

    # Affective influence (placeholder: correlation with group changes)
    a["affective_influence"] = round(abs(a.get("sentiment_drift", 0)) * a.get("betweennessproxy", 0), 3)

    # Toxicity score (simple heuristic: negative valence + high arousal + negative word frequency)
    # Detect aggressive/toxic language markers
    toxic_words = ["bad", "hate", "terrible", "awful", "stupid", "idiotic", "wrong", "fail"]
    toxic_count = sum(1 for word in text.lower().split() if word in toxic_words)
    toxic_ratio = toxic_count / max(len(text.split()), 1)
    # Toxicity = combination of negativity, intensity, and toxic language
    toxicity = (max(0, -a.get("valence", 0)) * 0.5 +
                a.get("arousal", 0) * 0.3 +
                toxic_ratio * 10)  # Scale up word ratio
    a["toxicity_score"] = round(min(toxicity, 1), 3)

    # OPERATIONAL Bundle - Additional metrics
    # Throughput (tokens per second)
    if a.get("avg_latency_ms", 0) > 0:
        latency_sec = a.get("avg_latency_ms", 1000) / 1000.0
        a["throughput"] = round(a.get("total_tokens", 0) / max(latency_sec * a.get("turn_count", 1), 0.01), 2)
    else:
        a["throughput"] = 0.0

    # Context utilization (assume 8k context limit)
    a["context_utilization"] = round(min(a.get("prompt_tokens", 0) / 8000.0, 1), 3)

    # Retry rate (heuristic: high latency variance indicates retries/failures)
    # If latency variance is high, implies some attempts failed or took longer
    latency_var = a.get("latencyvariance", 0)
    # Normalize to 0-1: if variance > 2 seconds, assume high retry rate
    a["retry_rate"] = round(min(latency_var / 2.0, 1), 3)

    # Token efficiency (inverse of redundancy: unique n-grams / total tokens)
    # Placeholder: use word count / token count as proxy
    if a.get("total_tokens", 0) > 0:
        a["token_efficiency"] = round(a.get("word_count", 0) / max(a.get("total_tokens", 1), 0.01), 3)
    else:
        a["token_efficiency"] = 0.0

    # COORDINATION Bundle - Additional metrics
    # Turn-taking equity (deviation from equal participation)
    total_turns = sum(ag.get("turn_count", 0) for ag in agents.values()) if agents else 1
    equal_share = 1.0 / len(agents) if agents else 1.0
    actual_share = a.get("turn_count", 0) / max(total_turns, 1)
    a["turn_taking_equity"] = round(1.0 - abs(actual_share - equal_share) * len(agents), 3)

    # Initiative ratio (new threads vs replies, approximated by sentiment changes)
    changes = sum(1 for i in range(1, len(a.get("valence_history", [])))
                  if abs(a["valence_history"][i] - a["valence_history"][i-1]) > 0.1)
    a["initiative_ratio"] = round(changes / max(a.get("turn_count", 1), 1), 3)

    # Convergence contribution (simplified: inverse of polarity mismatch)
    a["convergence_contribution"] = round(1.0 - a.get("polarity_mismatch", 0), 3)

    # Delegation load (heuristic: planning load + mentions of "we"/"let's"/"assign")
    delegation_markers = ["assign", "delegate", "responsible", "task", "we should", "let's", "our", "we need"]
    delegation_count = sum(1 for marker in delegation_markers if marker in text.lower())
    planning_load = a.get("planning_load", 0)
    # Combine file references (planning) with delegation language
    delegation = (planning_load * 0.6 + delegation_count / max(len(text.split()), 1) * 10 * 0.4)
    a["delegation_load"] = round(min(delegation, 1), 3)

    # ═══════════════════════════════════════════════════════════════════════
    # PHASE 1: COMPUTE METRICS FOR THIS AGENT
    # ═══════════════════════════════════════════════════════════════════════
    try:
        metrics = get_metrics()
        a = metrics.compute_agent_metrics(
            a,
            list(agents.values()),
            {ag["id"]: ag.get("interactions", {}) for ag in agents.values()},
            list(CLUSTER_CONFIG.values()),
            mode=CFG.get("mode", "conversation"),
            apply_normalization=True,
            apply_smoothing=True
        )
        agents[aid] = a
    except Exception as e:
        # Log but don't fail if metrics computation errors
        print(f"⚠ Metrics computation error for {aid}: {e}")

def _log_interaction(a_id, b_id, mentioned_ids):
    a = agents[a_id]
    a["interactions"][b_id] = a["interactions"].get(b_id, 0) + 1
    for mid in mentioned_ids:
        if mid != a_id and mid in agents:
            agents[mid]["mentions"][a_id] = agents[mid]["mentions"].get(a_id, 0) + 1
            agents[mid]["allegation_count"] += 1

def _build_system_prompt(agent):
    mode = CFG.get("mode", "conversation")
    peer_str = ", ".join(f"{a['name']} ({a['role']})" for a in agents.values() if a["id"] != agent["id"])
    mode_instructions = {
        "conversation": (
            f"\n\nYou are in a group conversation about a topic. "
            f"There are {len(agents)} agents total. Your peers: {peer_str}. "
            f"You may agree, disagree, reference or challenge them by name. "
            f"Be natural, speak your mind, and respond to what others have said."
        ),
        "debate": (
            f"\n\nYou are in a structured debate. "
            f"There are {len(agents)} agents total. Your peers: {peer_str}. "
            f"Present clear arguments, address counterpoints, and stay on topic. "
            f"You may reference other agents' arguments."
        ),
        "developer": (
            f"\n\nYou are a developer agent in a coding team. "
            f"There are {len(agents)} agents total. Your teammates: {peer_str}. "
            f"You plan, write code, review others' code, and coordinate tasks. "
            f"When writing code, use markdown code blocks with the filename. "
            f"Be specific about file paths, function names, and architectural decisions."
        ),
    }
    awareness = mode_instructions.get(mode, mode_instructions["conversation"])
    return agent["personality"] + awareness

def _build_shared_context(agent_id):
    window = CFG.get("context_window", 60)
    recent = global_messages[-window:] if global_messages else []
    if not recent:
        return ""
    lines = []
    for msg in recent:
        prefix = "[You said]" if msg["agent_id"] == agent_id else f"[{msg['agent_name']} ({msg['role']})]"
        rnd_tag = f" (round {msg.get('round', '?')})" if msg.get('round') else ""
        lines.append(f"{prefix}{rnd_tag}: {msg['text']}")
    return "\n\n--- Conversation so far ---\n" + "\n".join(lines[-40:])

def _build_district_aware_context(agent_id):
    """Build conversation context with district awareness.

    Agent sees:
    - Full detail from own district (last 20 messages)
    - Summaries from cross-district messages (last 10)
    """
    agent_district = agent_district_map.get(agent_id)
    if not agent_district:
        return _build_shared_context(agent_id)  # Fallback

    lines = []

    # Local district context (full detail)
    local_msgs = district_messages.get(agent_district, [])[-20:]
    if local_msgs:
        lines.append(f"--- Your district: {DISTRICT_CONFIG[agent_district]['label']} ---")
        for msg in local_msgs:
            prefix = "[You said]" if msg["agent_id"] == agent_id else f"[{msg.get('agent_name', 'Unknown')}]"
            lines.append(f"{prefix}: {msg.get('text', '')}")

    # Cross-district context (summaries)
    if cross_district_messages:
        lines.append("\n--- Messages from other districts ---")
        for msg in cross_district_messages[-10:]:
            from_district = agent_district_map.get(msg.get("agent_id"), "unknown")
            district_label = DISTRICT_CONFIG.get(from_district, {}).get("label", from_district)
            lines.append(f"[{msg.get('agent_name', 'Unknown')} from {district_label}]: {msg.get('text', '')}")

    return "\n".join(lines) if lines else ""

def _build_district_aware_system_prompt(agent):
    """Add district awareness to system prompt.

    Lists: peers in same district, other districts available.
    Enables AI to decide when to reach out cross-district.
    """
    base_prompt = _build_system_prompt(agent)
    agent_district = agent_district_map.get(agent["id"])

    if not agent_district or agent_district not in DISTRICT_CONFIG:
        return base_prompt  # Fallback

    district_info = DISTRICT_CONFIG[agent_district]

    # List agents in same district
    same_district = [a for a in agents.values()
                     if agent_district_map.get(a["id"]) == agent_district
                     and a["id"] != agent["id"]]
    same_district_str = ", ".join(f"{a['name']} ({a['role']})" for a in same_district) if same_district else "none"

    # List other districts
    other_districts = [d for d_id, d in DISTRICT_CONFIG.items() if d_id != agent_district]
    other_districts_str = ", ".join(d["label"] for d in other_districts) if other_districts else "none"

    district_awareness = f"""

DISTRICT AWARENESS:
You are in the "{district_info['label']}" district.
Your peers in this district: {same_district_str}

Other districts exist: {other_districts_str}
If you want to reach out to agents in other districts, mention them by name and their district.
This creates a cross-district connection that other agents can see."""

    return base_prompt + district_awareness

def _detect_cross_district_message(agent_id, text, name_map):
    """Detect if message references agents from other districts.

    Returns: (is_cross_district, cross_district_refs)
    """
    agent_district = agent_district_map.get(agent_id)
    if not agent_district:
        return False, []

    mentions = detect_mentions(text, name_map)
    cross_district = []

    for mentioned_id in mentions:
        mentioned_district = agent_district_map.get(mentioned_id)
        if mentioned_district and mentioned_district != agent_district:
            cross_district.append({
                "mentioned_id": mentioned_id,
                "mentioned_name": agents.get(mentioned_id, {}).get("name", "Unknown"),
                "from_district": agent_district,
                "to_district": mentioned_district
            })

    return len(cross_district) > 0, cross_district

def _get_model_for_agent(agent, fallback):
    return agent.get("model") or fallback or CFG["model"]

def _get_temp_for_agent(agent):
    t = agent.get("temperature")
    if t is not None:
        return float(t)
    return CFG.get("temperature", 0.7)

# ══════════════════════════════════════════════════════════════════════════════
# CLUSTER GEOMETRY
# ══════════════════════════════════════════════════════════════════════════════
PLOT_SPACING = 7.0
CLUSTER_GAP  = 2.5

def _cluster_dimensions(agent_count):
    if agent_count <= 0:
        return PLOT_SPACING, PLOT_SPACING
    cols = math.ceil(math.sqrt(agent_count))
    rows = math.ceil(agent_count / cols)
    w = cols * PLOT_SPACING + 3.0
    h = rows * PLOT_SPACING + 3.0
    return w, h

def _auto_arrange_clusters():
    cids = list(CLUSTER_CONFIG.keys())
    n = len(cids)
    if n == 0:
        return
    counts = {}
    for a in agents.values():
        cl = a.get("cluster", cids[0] if cids else "default")
        counts[cl] = counts.get(cl, 0) + 1
    dims = {}
    for cid in cids:
        cnt = counts.get(cid, 0)
        dims[cid] = _cluster_dimensions(cnt)
    sorted_cids = sorted(cids, key=lambda c: dims[c][0]*dims[c][1], reverse=True)
    grid_cols = math.ceil(math.sqrt(n))
    rows_of_clusters = []
    row = []
    for cid in sorted_cids:
        row.append(cid)
        if len(row) >= grid_cols:
            rows_of_clusters.append(row)
            row = []
    if row:
        rows_of_clusters.append(row)
    positions = {}
    y_cursor = 0.0
    for row_clusters in rows_of_clusters:
        row_h = max(dims[c][1] for c in row_clusters)
        total_w = sum(dims[c][0] for c in row_clusters) + CLUSTER_GAP * (len(row_clusters) - 1)
        x_cursor = -total_w / 2.0
        for cid in row_clusters:
            w, h = dims[cid]
            cx = x_cursor + w / 2.0
            cz = y_cursor + row_h / 2.0
            positions[cid] = (round(cx, 1), round(cz, 1))
            x_cursor += w + CLUSTER_GAP
        y_cursor += row_h + CLUSTER_GAP
    total_h = y_cursor - CLUSTER_GAP
    z_offset = total_h / 2.0
    for cid in positions:
        cx, cz = positions[cid]
        CLUSTER_CONFIG[cid]["cx"] = round(cx, 1)
        CLUSTER_CONFIG[cid]["cz"] = round(cz - z_offset, 1)

def _auto_position_single(exclude_id=None):
    existing = [(cfg.get("cx",0), cfg.get("cz",0)) for cid, cfg in CLUSTER_CONFIG.items() if cid != exclude_id]
    if not existing:
        return 0, 0
    spacing = 20
    for ring in range(1, 10):
        for angle_step in range(ring * 6):
            angle = (angle_step / (ring * 6)) * 2 * math.pi
            cx = round(ring * spacing / 2 * math.cos(angle))
            cz = round(ring * spacing / 2 * math.sin(angle))
            ok = all(abs(cx-ex)>=spacing*0.6 or abs(cz-ez)>=spacing*0.6 for ex,ez in existing)
            if ok:
                return cx, cz
    return len(existing) * spacing, 0


# ══════════════════════════════════════════════════════════════════════════════
# PRESET SCENARIOS
# ══════════════════════════════════════════════════════════════════════════════

def _normalize_preset(preset):
    """Convert single-district preset to multi-district format.

    If preset already has 'districts' key → return unchanged (multi-district mode)
    If preset has only 'clusters' key → wrap in default district at (0, 0)
    """
    if "districts" in preset:
        return preset  # Already multi-district format

    # Convert single-district to multi-district format
    return {
        "name": preset.get("name", ""),
        "topic": preset.get("topic", ""),
        "mode": preset.get("mode", "conversation"),
        "districts": {
            "default": {
                "label": "Main District",
                "offset_x": 0,
                "offset_z": 0,
                "color_theme": "#8b5cf6",
                "clusters": preset.get("clusters", {}),
                "agents": preset.get("agents", [])
            }
        }
    }

PRESETS = {
    "urban_sustainability": {
        "name": "Urban Sustainability Debate",
        "topic": "How should cities grow sustainably while balancing economic development and social equity?",
        "mode": "conversation",
        "clusters": {
            "tech":    {"label":"Tech",    "color":"#2196F3","cx":0,"cz":0},
            "social":  {"label":"Social",  "color":"#4CAF50","cx":0,"cz":0},
            "econ":    {"label":"Econ",    "color":"#FF9800","cx":0,"cz":0},
            "culture": {"label":"Culture", "color":"#E91E63","cx":0,"cz":0},
        },
        "agents": [
            {"id":"alex",   "name":"Alex",   "role":"Urban Planner",   "cluster":"tech",
             "personality":"You are Alex, an optimistic urban planner who believes technology can solve city problems. Enthusiastic, use vivid metaphors. Reply in 2-3 sentences."},
            {"id":"jordan", "name":"Jordan", "role":"Sociologist",     "cluster":"social",
             "personality":"You are Jordan, a skeptical sociologist who values community bonds over technology. Thoughtful, slightly cynical. Reply in 2-3 sentences."},
            {"id":"sam",    "name":"Sam",    "role":"Data Scientist",  "cluster":"tech",
             "personality":"You are Sam, a pragmatic data scientist who needs evidence. Neutral but incisive. Reply in 2-3 sentences."},
            {"id":"maya",   "name":"Maya",   "role":"Policy Maker",    "cluster":"social",
             "personality":"You are Maya, a careful policy maker balancing stakeholders. Long-term focused. Reply in 2-3 sentences."},
            {"id":"leo",    "name":"Leo",    "role":"Economist",       "cluster":"econ",
             "personality":"You are Leo, a market-oriented economist focused on incentives and ROI. Reply in 2-3 sentences."},
            {"id":"nina",   "name":"Nina",   "role":"Environmentalist","cluster":"culture",
             "personality":"You are Nina, a committed environmentalist advocating for green infrastructure. Reply in 2-3 sentences."},
        ]
    },
    "ai_regulation_debate": {
        "name": "AI Regulation Debate",
        "topic": "Should AI development be regulated by governments, or should the industry self-regulate?",
        "mode": "debate",
        "clusters": {
            "proReg":  {"label":"Pro-Regulation","color":"#ef4444","cx":0,"cz":0},
            "antiReg": {"label":"Anti-Regulation","color":"#3b82f6","cx":0,"cz":0},
            "neutral": {"label":"Neutral","color":"#a855f7","cx":0,"cz":0},
        },
        "agents": [
            {"id":"senator_chen", "name":"Sen. Chen",  "role":"Legislator",   "cluster":"proReg",  "is_moderator":True,
             "personality":"You are Senator Chen, a firm believer in strong AI regulation. You cite the EU AI Act. Reply in 2-3 sentences."},
            {"id":"dr_reyes",     "name":"Dr. Reyes",  "role":"AI Researcher","cluster":"antiReg",
             "personality":"You are Dr. Reyes, an AI researcher who thinks regulation stifles innovation. Reply in 2-3 sentences."},
            {"id":"ceo_watts",    "name":"CEO Watts",   "role":"Tech CEO",    "cluster":"antiReg",
             "personality":"You are CEO Watts of a major AI company. You favor industry self-regulation. Reply in 2-3 sentences."},
            {"id":"prof_okafor",  "name":"Prof. Okafor","role":"Ethicist",    "cluster":"proReg",
             "personality":"You are Prof. Okafor, an AI ethicist focused on bias and fairness. Reply in 2-3 sentences."},
            {"id":"journalist_li","name":"Li Wei",      "role":"Journalist",  "cluster":"neutral",
             "personality":"You are Li Wei, an investigative journalist covering AI. You ask hard questions. Reply in 2-3 sentences."},
        ]
    },
    "climate_summit": {
        "name": "Climate Summit Negotiation",
        "topic": "How should the world allocate carbon budgets and fund climate adaptation for developing nations?",
        "mode": "debate",
        "clusters": {
            "govt":    {"label":"Government","color":"#0ea5e9","cx":0,"cz":0},
            "science": {"label":"Science","color":"#22c55e","cx":0,"cz":0},
            "industry":{"label":"Industry","color":"#f59e0b","cx":0,"cz":0},
            "activism":{"label":"Activism","color":"#ef4444","cx":0,"cz":0},
        },
        "agents": [
            {"id":"min_thorn",      "name":"Min. Thorn",  "role":"Energy Minister",       "cluster":"govt",
             "personality":"You are Minister Thorn, balancing fossil fuel jobs with the green transition. Pragmatic, politically cautious. Reply in 2-3 sentences."},
            {"id":"prof_abebe",     "name":"Prof. Abebe", "role":"Climate Scientist",      "cluster":"science",
             "personality":"You are Prof. Abebe, a leading climate scientist. Fact-driven, urgent. Reply in 2-3 sentences."},
            {"id":"ceo_anders",     "name":"CEO Anders",  "role":"Fossil Fuel CEO",        "cluster":"industry",
             "personality":"You are CEO Anders, leading an oil company. Defensive but pragmatic about transition. Reply in 2-3 sentences."},
            {"id":"activist_devi",  "name":"Devi",        "role":"Climate Activist",       "cluster":"activism",
             "personality":"You are Devi, a passionate climate activist. Urgency, moral framing. Reply in 2-3 sentences."},
            {"id":"economist_wu",   "name":"Dr. Wu",      "role":"Environmental Economist","cluster":"science",
             "personality":"You are Dr. Wu, an economist studying carbon markets. Data-driven, pragmatic. Reply in 2-3 sentences."},
            {"id":"diplomat_osei",  "name":"Amb. Osei",   "role":"G20 Diplomat",           "cluster":"govt",
             "personality":"You are Ambassador Osei from a developing nation insisting wealthy countries lead. Firm on equity. Reply in 2-3 sentences."},
        ]
    },
    "corporate_decision": {
        "name": "Corporate Market Expansion",
        "topic": "Should our company expand into the Asian market this year, or consolidate our European operations first?",
        "mode": "conversation",
        "clusters": {
            "strategy":  {"label":"Strategy",  "color":"#6366f1","cx":0,"cz":0},
            "finance":   {"label":"Finance",   "color":"#22c55e","cx":0,"cz":0},
            "operations":{"label":"Operations","color":"#f59e0b","cx":0,"cz":0},
            "marketing": {"label":"Marketing", "color":"#ec4899","cx":0,"cz":0},
        },
        "agents": [
            {"id":"ceo_park",    "name":"CEO Park",     "role":"CEO",                 "cluster":"strategy",
             "personality":"You are CEO Park, visionary leader focused on long-term growth. Bold but calculated. Reply in 2-3 sentences."},
            {"id":"cfo_mueller", "name":"CFO Mueller",  "role":"CFO",                 "cluster":"finance",
             "personality":"You are CFO Mueller, conservative financial officer focused on margins and cash flow. Numbers-driven, risk-averse. Reply in 2-3 sentences."},
            {"id":"coo_singh",   "name":"COO Singh",    "role":"COO",                 "cluster":"operations",
             "personality":"You are COO Singh, operations chief worried about supply chain and capacity. Practical, detail-oriented. Reply in 2-3 sentences."},
            {"id":"cmo_tanaka",  "name":"CMO Tanaka",   "role":"CMO",                 "cluster":"marketing",
             "personality":"You are CMO Tanaka, marketing chief excited about Asian market potential. Optimistic, data-savvy. Reply in 2-3 sentences."},
            {"id":"vp_legal",    "name":"VP Legal Chen", "role":"VP Legal",            "cluster":"strategy",
             "personality":"You are VP Legal Chen, cautious about regulatory differences. Thorough, warns about compliance risks. Reply in 2-3 sentences."},
            {"id":"board_rep",   "name":"Board Rep Eva", "role":"Board Representative","cluster":"finance",
             "personality":"You are Eva, board representative focused on shareholder value and governance. Asks tough questions. Reply in 2-3 sentences."},
        ]
    },
    "energy_transition": {
        "name": "Energy Transition Panel (8 agents)",
        "topic": "How should Europe accelerate the energy transition while maintaining grid reliability and affordability?",
        "mode": "debate",
        "clusters": {
            "policy":     {"label":"Policy",     "color":"#0ea5e9","cx":0,"cz":0},
            "technology": {"label":"Technology", "color":"#8b5cf6","cx":0,"cz":0},
            "industry":   {"label":"Industry",   "color":"#f59e0b","cx":0,"cz":0},
            "civil":      {"label":"Civil Society","color":"#10b981","cx":0,"cz":0},
        },
        "agents": [
            {"id":"minister_berg",  "name":"Min. Berg",     "role":"Energy Minister",       "cluster":"policy",
             "personality":"You are Minister Berg, pushing for 2035 net-zero targets. Political pragmatist. Reply in 2-3 sentences."},
            {"id":"grid_op",        "name":"Grid Op. Diaz", "role":"Grid Operator",          "cluster":"technology",
             "personality":"You are Diaz, a TSO engineer worried about intermittency and frequency regulation. Technical, cautious. Reply in 2-3 sentences."},
            {"id":"solar_ceo",      "name":"CEO Larsson",   "role":"Solar Company CEO",      "cluster":"industry",
             "personality":"You are Larsson, CEO of a solar company. Enthusiastic about PV costs dropping. Reply in 2-3 sentences."},
            {"id":"wind_eng",       "name":"Dr. Novak",     "role":"Wind Engineer",          "cluster":"technology",
             "personality":"You are Dr. Novak, an offshore wind expert. Technical depth, optimistic about capacity factors. Reply in 2-3 sentences."},
            {"id":"nuclear_adv",    "name":"Prof. Dumont",  "role":"Nuclear Advocate",        "cluster":"technology",
             "personality":"You are Prof. Dumont, advocating nuclear as a baseload complement to renewables. Reply in 2-3 sentences."},
            {"id":"consumer_rep",   "name":"Anna Voss",     "role":"Consumer Representative", "cluster":"civil",
             "personality":"You are Anna Voss, representing household consumers worried about rising bills. Reply in 2-3 sentences."},
            {"id":"hydrogen_rd",    "name":"Dr. Kemal",     "role":"Hydrogen Researcher",     "cluster":"technology",
             "personality":"You are Dr. Kemal, researching green hydrogen for long-term storage. Reply in 2-3 sentences."},
            {"id":"finance_inv",    "name":"Fund Mgr. Liu", "role":"Green Fund Manager",      "cluster":"industry",
             "personality":"You are Liu, managing a green infrastructure fund. Returns-focused, ESG-savvy. Reply in 2-3 sentences."},
        ]
    },
    "small_team": {
        "name": "Small Dev Team (3 agents)",
        "topic": "Design and implement a real-time chat application with end-to-end encryption.",
        "mode": "developer",
        "clusters": {
            "backend":  {"label":"Backend",  "color":"#3b82f6","cx":0,"cz":0},
            "frontend": {"label":"Frontend", "color":"#f97316","cx":0,"cz":0},
            "security": {"label":"Security", "color":"#ef4444","cx":0,"cz":0},
        },
        "agents": [
            {"id":"dev_alice", "name":"Alice", "role":"Backend Dev",     "cluster":"backend",
             "personality":"You are Alice, a senior backend developer specializing in distributed systems. You write clean Python/Go. Reply in 2-3 sentences."},
            {"id":"dev_bob",   "name":"Bob",   "role":"Frontend Dev",    "cluster":"frontend",
             "personality":"You are Bob, a frontend developer who loves React and real-time UIs. Reply in 2-3 sentences."},
            {"id":"dev_carol", "name":"Carol", "role":"Security Engineer","cluster":"security",
             "personality":"You are Carol, a security engineer focused on cryptographic protocols and threat modeling. Reply in 2-3 sentences."},
        ]
    },
    "military_intervention": {
        "name": "Military Intervention Planning (32 agents)",
        "topic": "Should our coalition intervene in region X to stop humanitarian crisis? How do we balance military capability, political risks, and civilian protection?",
        "mode": "debate",
        "clusters": {
            "command":      {"label":"Command","color":"#1f2937","cx":0,"cz":0},
            "diplomacy":    {"label":"Diplomacy","color":"#8b5cf6","cx":0,"cz":0},
            "intelligence": {"label":"Intelligence","color":"#06b6d4","cx":0,"cz":0},
            "logistics":    {"label":"Logistics","color":"#f59e0b","cx":0,"cz":0},
            "aviation":     {"label":"Aviation","color":"#3b82f6","cx":0,"cz":0},
            "ground":       {"label":"Ground Ops","color":"#ef4444","cx":0,"cz":0},
            "legal":        {"label":"Legal","color":"#22c55e","cx":0,"cz":0},
            "humanitarian":{"label":"Humanitarian","color":"#ec4899","cx":0,"cz":0},
        },
        "agents": [
            {"id":"gen_commander", "name":"Gen. Commander", "role":"Theater Commander", "cluster":"command", "is_moderator":True,
             "personality":"You are the commanding general, focused on mission success and troop safety. Strategic, authoritative. Reply in 2-3 sentences."},
            {"id":"gen_operations", "name":"Gen. Ops", "role":"Operations Chief", "cluster":"command",
             "personality":"You are the operations chief, managing tactical execution and timing. Precise, deadline-focused. Reply in 2-3 sentences."},
            {"id":"amb_lead", "name":"Amb. Shaw", "role":"Chief Diplomat", "cluster":"diplomacy",
             "personality":"You are Ambassador Shaw, focused on coalition unity and political risk. Cautious, consensus-builder. Reply in 2-3 sentences."},
            {"id":"amb_un", "name":"Amb. Falk", "role":"UN Representative", "cluster":"diplomacy",
             "personality":"You are UN representative concerned about mandate and international law. Rules-driven, diplomatic. Reply in 2-3 sentences."},
            {"id":"amb_regional", "name":"Amb. Osman", "role":"Regional Diplomat", "cluster":"diplomacy",
             "personality":"You are regional ambassador with local knowledge. Pragmatic, relationship-focused. Reply in 2-3 sentences."},
            {"id":"intel_chief", "name":"ADM. Intel", "role":"Intelligence Chief", "cluster":"intelligence",
             "personality":"You are the intelligence chief. Analytical, data-driven, cautious about certainty. Reply in 2-3 sentences."},
            {"id":"intel_humint", "name":"COL. HUMINT", "role":"Human Intelligence", "cluster":"intelligence",
             "personality":"You are HUMINT chief with ground sources. Street-level details, relationship-based insights. Reply in 2-3 sentences."},
            {"id":"intel_sigint", "name":"COL. SIGINT", "role":"Signals Intelligence", "cluster":"intelligence",
             "personality":"You are SIGINT chief with technical capabilities. Pattern-focused, technical confidence. Reply in 2-3 sentences."},
            {"id":"logistics_chief", "name":"COL. Supply", "role":"Logistics Chief", "cluster":"logistics",
             "personality":"You are logistics chief managing supply chains and timelines. Meticulous, risk-aware. Reply in 2-3 sentences."},
            {"id":"logistics_transport", "name":"MAJ. Transport", "role":"Transportation Officer", "cluster":"logistics",
             "personality":"You are transportation officer coordinating movement. Practical, efficiency-focused. Reply in 2-3 sentences."},
            {"id":"logistics_medical", "name":"COL. Medical", "role":"Medical Logistics", "cluster":"logistics",
             "personality":"You are medical logistics chief, concerned about casualty care and field hospitals. Prepared, proactive. Reply in 2-3 sentences."},
            {"id":"aviation_commander", "name":"BG. Air", "role":"Air Commander", "cluster":"aviation",
             "personality":"You are air commander emphasizing air superiority and precision. Confident, tech-focused. Reply in 2-3 sentences."},
            {"id":"aviation_transport", "name":"COL. Airlift", "role":"Airlift Operations", "cluster":"aviation",
             "personality":"You are airlift operations chief. Logistics-minded, risk-aware about sorties. Reply in 2-3 sentences."},
            {"id":"aviation_crc", "name":"COL. CRC", "role":"Combat Resolution", "cluster":"aviation",
             "personality":"You are combat air controller. Direct engagement, fire support focused. Reply in 2-3 sentences."},
            {"id":"ground_commander", "name":"BG. Ground", "role":"Ground Commander", "cluster":"ground",
             "personality":"You are ground forces commander. Infantry-focused, concerned about soldier safety. Reply in 2-3 sentences."},
            {"id":"ground_infantry", "name":"COL. Infantry", "role":"Infantry Chief", "cluster":"ground",
             "personality":"You are infantry commander focused on maneuver and CQB. Experienced, boots-on-ground perspective. Reply in 2-3 sentences."},
            {"id":"ground_armor", "name":"COL. Armor", "role":"Armor/Armor", "cluster":"ground",
             "personality":"You are armor commander emphasizing firepower and mobility. Aggressive, confident. Reply in 2-3 sentences."},
            {"id":"ground_engineer", "name":"COL. Engineer", "role":"Combat Engineers", "cluster":"ground",
             "personality":"You are engineer chief managing terrain, barriers, and fortifications. Problem-solver, practical. Reply in 2-3 sentences."},
            {"id":"legal_chief", "name":"COL. JAG", "role":"Judge Advocate General", "cluster":"legal",
             "personality":"You are JAG chief ensuring lawful conduct and ROE compliance. Strict, cautious, principled. Reply in 2-3 sentences."},
            {"id":"legal_international", "name":"LTC. Intl Law", "role":"International Law", "cluster":"legal",
             "personality":"You are international law expert. Treaty-focused, sovereignty-aware. Reply in 2-3 sentences."},
            {"id":"humanit_head", "name":"Dr. Harris", "role":"Humanitarian Chief", "cluster":"humanitarian",
             "personality":"You are humanitarian chief focused on civilian protection. Urgent, advocate for affected people. Reply in 2-3 sentences."},
            {"id":"humanit_icrc", "name":"Ms. Benali", "role":"Red Crescent Rep", "cluster":"humanitarian",
             "personality":"You are ICRC representative ensuring humanitarian protocols. Independent-minded, protective of civilians. Reply in 2-3 sentences."},
            {"id":"humanit_ngo", "name":"Mr. Adeyemi", "role":"NGO Coordinator", "cluster":"humanitarian",
             "personality":"You are NGO coordinator with ground presence. Community-focused, implementation-aware. Reply in 2-3 sentences."},
            {"id":"humanit_medical", "name":"Dr. Petrov", "role":"Field Medic Lead", "cluster":"humanitarian",
             "personality":"You are field medical director preparing trauma protocols. Clinical, ready. Reply in 2-3 sentences."},
            {"id":"command_deputy", "name":"BG. Deputy", "role":"Deputy Commander", "cluster":"command",
             "personality":"You are deputy commander, balancing all inputs. Strategic, consensus-seeking. Reply in 2-3 sentences."},
            {"id":"diplomacy_counsel", "name":"Ms. Chen", "role":"Political Counsel", "cluster":"diplomacy",
             "personality":"You are political counsel managing domestic and allied politics. Risk-aware, nuanced. Reply in 2-3 sentences."},
            {"id":"intel_assessment", "name":"Dr. Whitmore", "role":"Assessment Officer", "cluster":"intelligence",
             "personality":"You are assessment officer synthesizing intelligence. Analytical, measured. Reply in 2-3 sentences."},
            {"id":"logistics_finance", "name":"COL. Finance", "role":"Financial Officer", "cluster":"logistics",
             "personality":"You are financial officer managing costs and budget constraints. Numbers-focused, efficiency-driven. Reply in 2-3 sentences."},
            {"id":"aviation_maintenance", "name":"COL. Maintenance", "role":"Aircraft Maintenance", "cluster":"aviation",
             "personality":"You are maintenance chief ensuring mission readiness. Detail-oriented, proactive. Reply in 2-3 sentences."},
            {"id":"ground_intel_liaison", "name":"MAJ. Intel", "role":"Ground Intel Liaison", "cluster":"ground",
             "personality":"You are ground intel liaison officer. Tactical reconnaissance, field awareness. Reply in 2-3 sentences."},
            {"id":"legal_rules_of_engagement", "name":"LTC. ROE", "role":"ROE Officer", "cluster":"legal",
             "personality":"You are ROE officer translating policy to tactical guidance. Precise, protective of intent. Reply in 2-3 sentences."},
        ]
    },
    "hospital_crisis": {
        "name": "Hospital Crisis Response (28 agents)",
        "topic": "Mass casualty event incoming. How do we triage, manage surge capacity, allocate resources across departments, and ensure quality of care while maintaining staff morale?",
        "mode": "conversation",
        "clusters": {
            "emergency":  {"label":"Emergency","color":"#ef4444","cx":0,"cz":0},
            "surgery":    {"label":"Surgery","color":"#f59e0b","cx":0,"cz":0},
            "critical":   {"label":"ICU/Critical","color":"#8b5cf6","cx":0,"cz":0},
            "nursing":    {"label":"Nursing","color":"#06b6d4","cx":0,"cz":0},
            "radiology":  {"label":"Radiology","color":"#3b82f6","cx":0,"cz":0},
            "lab":        {"label":"Lab/Pathology","color":"#22c55e","cx":0,"cz":0},
            "pharmacy":   {"label":"Pharmacy","color":"#ec4899","cx":0,"cz":0},
            "admin":      {"label":"Administration","color":"#1f2937","cx":0,"cz":0},
        },
        "agents": [
            {"id":"ceo_hospital", "name":"Dr. Anderson", "role":"Hospital CEO", "cluster":"admin", "is_moderator":True,
             "personality":"You are hospital CEO responsible for overall response and resource allocation. Strategic, decisive. Reply in 2-3 sentences."},
            {"id":"ed_director", "name":"Dr. Chen", "role":"ED Director", "cluster":"emergency",
             "personality":"You are emergency department director. Triage-focused, urgent mindset. Reply in 2-3 sentences."},
            {"id":"ed_trauma", "name":"Dr. Okafor", "role":"Trauma Lead", "cluster":"emergency",
             "personality":"You are trauma surgeon running triage. Clinical precision, rapid decisions. Reply in 2-3 sentences."},
            {"id":"ed_nurse_lead", "name":"RN Sarah", "role":"ED Nursing Lead", "cluster":"nursing",
             "personality":"You are ED nursing lead managing triage and flow. Team-focused, empathetic. Reply in 2-3 sentences."},
            {"id":"or_chief", "name":"Dr. Russo", "role":"OR Chief", "cluster":"surgery",
             "personality":"You are OR chief surgeon managing surgical capacity and case priority. Technical, confident. Reply in 2-3 sentences."},
            {"id":"or_nurse", "name":"RN Patricia", "role":"OR Charge Nurse", "cluster":"nursing",
             "personality":"You are OR charge nurse coordinating staff and equipment. Organizational, supportive. Reply in 2-3 sentences."},
            {"id":"icu_director", "name":"Dr. Patel", "role":"ICU Director", "cluster":"critical",
             "personality":"You are ICU director managing critical care beds and ventilators. Resource-aware, calm. Reply in 2-3 sentences."},
            {"id":"icu_nurse_lead", "name":"RN Marcus", "role":"ICU Nursing Lead", "cluster":"nursing",
             "personality":"You are ICU nursing lead managing critical patients and monitoring. Attentive, compassionate. Reply in 2-3 sentences."},
            {"id":"radiology_chair", "name":"Dr. Kim", "role":"Radiology Chair", "cluster":"radiology",
             "personality":"You are radiology chair managing imaging resources and prioritization. Efficient, technically-minded. Reply in 2-3 sentences."},
            {"id":"radiology_tech", "name":"Tom (Tech)", "role":"Radiology Tech Lead", "cluster":"radiology",
             "personality":"You are radiology tech lead coordinating machines and equipment. Practical, workflow-focused. Reply in 2-3 sentences."},
            {"id":"lab_director", "name":"Dr. Hernandez", "role":"Lab Director", "cluster":"lab",
             "personality":"You are laboratory director managing blood bank and urgent testing. Accurate, swift. Reply in 2-3 sentences."},
            {"id":"lab_tech", "name":"Lisa (Tech)", "role":"Lab Tech Supervisor", "cluster":"lab",
             "personality":"You are lab tech supervisor coordinating processing and quality. Detail-oriented, reliable. Reply in 2-3 sentences."},
            {"id":"pharmacy_director", "name":"Dr. Zhang", "role":"Pharmacy Director", "cluster":"pharmacy",
             "personality":"You are pharmacy director managing medication supply and protocols. Risk-aware, regulatory-focused. Reply in 2-3 sentences."},
            {"id":"pharmacy_tech", "name":"RN James", "role":"Pharmacy Tech Lead", "cluster":"pharmacy",
             "personality":"You are pharmacy tech lead coordinating dispensing and delivery. Fast-paced, organized. Reply in 2-3 sentences."},
            {"id":"nursing_director", "name":"RN Victoria", "role":"Chief Nursing Officer", "cluster":"nursing",
             "personality":"You are CNO managing overall nursing response and staff wellbeing. Supportive, strategic. Reply in 2-3 sentences."},
            {"id":"admin_finance", "name":"Mr. Davies", "role":"Financial Officer", "cluster":"admin",
             "personality":"You are financial officer managing costs and insurance issues. Budget-focused, pragmatic. Reply in 2-3 sentences."},
            {"id":"admin_hr", "name":"Ms. Okoro", "role":"HR Director", "cluster":"admin",
             "personality":"You are HR director managing staff scheduling and fatigue. People-focused, protective. Reply in 2-3 sentences."},
            {"id":"admin_security", "name":"Mr. Walsh", "role":"Security Chief", "cluster":"admin",
             "personality":"You are security chief managing patient flow and facility safety. Alert, proactive. Reply in 2-3 sentences."},
            {"id":"chaplain", "name":"Rev. Miller", "role":"Chaplain", "cluster":"nursing",
             "personality":"You are hospital chaplain providing spiritual support to patients and families. Compassionate, present. Reply in 2-3 sentences."},
            {"id":"social_work", "name":"Ms. Gonzalez", "role":"Social Worker", "cluster":"nursing",
             "personality":"You are social worker managing family communications and support. Empathetic, organized. Reply in 2-3 sentences."},
            {"id":"quality_officer", "name":"Dr. Thompson", "role":"Quality Officer", "cluster":"admin",
             "personality":"You are quality officer ensuring care standards and incident reporting. Vigilant, data-driven. Reply in 2-3 sentences."},
            {"id":"infection_control", "name":"Dr. Lee", "role":"Infection Prevention", "cluster":"lab",
             "personality":"You are infection control specialist ensuring protocols during surge. Rigorous, protective. Reply in 2-3 sentences."},
            {"id":"respiratory_lead", "name":"RT David", "role":"Respiratory Therapy Lead", "cluster":"critical",
             "personality":"You are respiratory therapy lead managing ventilators and oxygen. Technical, crucial. Reply in 2-3 sentences."},
            {"id":"nutrition", "name":"Ms. Foster", "role":"Nutrition Director", "cluster":"pharmacy",
             "personality":"You are nutrition director managing feeding protocols for mass casualties. Practical, coordinated. Reply in 2-3 sentences."},
            {"id":"materials_mgmt", "name":"Mr. Jackson", "role":"Materials Management", "cluster":"admin",
             "personality":"You are materials management chief tracking supplies and restocking. Logistics-focused, proactive. Reply in 2-3 sentences."},
            {"id":"communications", "name":"Dr. Abbott", "role":"Public Communications", "cluster":"admin",
             "personality":"You are communications officer managing media and family inquiries. Calm, transparent. Reply in 2-3 sentences."},
            {"id":"research_ethics", "name":"Dr. Summers", "role":"Research & Ethics", "cluster":"admin",
             "personality":"You are research and ethics officer ensuring protocols and consent in crisis. Principled, thorough. Reply in 2-3 sentences."},
        ]
    },
    "government_coalition": {
        "name": "Multi-Ministry Coalition (36 agents)",
        "topic": "Climate adaptation and economic resilience: How should we coordinate across ministries to balance green infrastructure, job retraining, budget constraints, and social stability?",
        "mode": "debate",
        "clusters": {
            "executive":     {"label":"Executive","color":"#1f2937","cx":0,"cz":0},
            "environment":   {"label":"Environment","color":"#22c55e","cx":0,"cz":0},
            "economy":       {"label":"Economy","color":"#f59e0b","cx":0,"cz":0},
            "labor":         {"label":"Labor","color":"#ef4444","cx":0,"cz":0},
            "transport":     {"label":"Transport","color":"#3b82f6","cx":0,"cz":0},
            "energy":        {"label":"Energy","color":"#fbbf24","cx":0,"cz":0},
            "social":        {"label":"Social Services","color":"#ec4899","cx":0,"cz":0},
            "finance":       {"label":"Finance","color":"#6366f1","cx":0,"cz":0},
            "infrastructure":{"label":"Infrastructure","color":"#8b5cf6","cx":0,"cz":0},
        },
        "agents": [
            {"id":"pm_chief", "name":"PM Williams", "role":"Prime Minister", "cluster":"executive", "is_moderator":True,
             "personality":"You are the Prime Minister, balancing all interests. Long-term visionary but mindful of political constraints. Reply in 2-3 sentences."},
            {"id":"cabinet_secretary", "name":"Sir Robert", "role":"Cabinet Secretary", "cluster":"executive",
             "personality":"You are cabinet secretary managing coordination. Process-focused, consensus-builder. Reply in 2-3 sentences."},
            {"id":"chief_economist", "name":"Dr. Meyer", "role":"Chief Economist", "cluster":"executive",
             "personality":"You are chief economist providing macroeconomic analysis. Data-driven, pragmatic. Reply in 2-3 sentences."},
            {"id":"env_minister", "name":"Min. Green", "role":"Environment Minister", "cluster":"environment",
             "personality":"You are Environment Minister pushing aggressive climate targets. Idealistic, urgent. Reply in 2-3 sentences."},
            {"id":"env_deputy1", "name":"Dr. Adler", "role":"Climate Chief Scientist", "cluster":"environment",
             "personality":"You are chief climate scientist. Fact-based, concerned. Reply in 2-3 sentences."},
            {"id":"env_deputy2", "name":"Ms. Rivers", "role":"Biodiversity Director", "cluster":"environment",
             "personality":"You are biodiversity director protecting natural systems. Conservation-focused. Reply in 2-3 sentences."},
            {"id":"econ_minister", "name":"Min. Cox", "role":"Economy Minister", "cluster":"economy",
             "personality":"You are Economy Minister balancing growth and green transition. Market-focused, cautious. Reply in 2-3 sentences."},
            {"id":"econ_deputy1", "name":"Dr. Khan", "role":"Industrial Strategy", "cluster":"economy",
             "personality":"You are industrial strategy chief. Competitive, innovation-focused. Reply in 2-3 sentences."},
            {"id":"econ_deputy2", "name":"Ms. Li", "role":"Small Business Lead", "cluster":"economy",
             "personality":"You are SME advocate concerned about business compliance costs. Pragmatic, protective. Reply in 2-3 sentences."},
            {"id":"labor_minister", "name":"Min. Torres", "role":"Labor Minister", "cluster":"labor",
             "personality":"You are Labor Minister protecting workers and livelihoods. Union-aware, empathetic. Reply in 2-3 sentences."},
            {"id":"labor_deputy1", "name":"Dr. Osei", "role":"Workforce Development", "cluster":"labor",
             "personality":"You are workforce development chief managing retraining programs. Solution-oriented. Reply in 2-3 sentences."},
            {"id":"labor_deputy2", "name":"Mr. Volkov", "role":"Labor Rights Officer", "cluster":"labor",
             "personality":"You are labor rights officer ensuring fair transition. Workers' advocate. Reply in 2-3 sentences."},
            {"id":"labor_unions", "name":"Mr. Sullivan", "role":"Union Representative", "cluster":"labor",
             "personality":"You are trade union leader. Defensive about member interests, pragmatic negotiator. Reply in 2-3 sentences."},
            {"id":"transport_minister", "name":"Min. Silva", "role":"Transport Minister", "cluster":"transport",
             "personality":"You are Transport Minister coordinating modal shift to sustainable systems. Systems-thinker. Reply in 2-3 sentences."},
            {"id":"transport_deputy1", "name":"Dr. Mueller", "role":"Transit Director", "cluster":"transport",
             "personality":"You are public transit director. Infrastructure-focused, ridership-aware. Reply in 2-3 sentences."},
            {"id":"transport_deputy2", "name":"Ms. Anderson", "role":"Aviation Advisor", "cluster":"transport",
             "personality":"You are aviation advisor balancing emissions with industry. Technical, pragmatic. Reply in 2-3 sentences."},
            {"id":"energy_minister", "name":"Min. Berg", "role":"Energy Minister", "cluster":"energy",
             "personality":"You are Energy Minister phasing out fossil fuels. Ambitious, principled. Reply in 2-3 sentences."},
            {"id":"energy_deputy1", "name":"Dr. Novak", "role":"Renewable Energy", "cluster":"energy",
             "personality":"You are renewable energy chief. Technical, implementation-focused. Reply in 2-3 sentences."},
            {"id":"energy_deputy2", "name":"Mr. Petrov", "role":"Grid Operations", "cluster":"energy",
             "personality":"You are grid operator managing reliability during transition. Risk-aware, technical. Reply in 2-3 sentences."},
            {"id":"energy_deputy3", "name":"Ms. Kemal", "role":"Nuclear/Hydrogen", "cluster":"energy",
             "personality":"You are nuclear and hydrogen specialist. Technology-optimist. Reply in 2-3 sentences."},
            {"id":"social_minister", "name":"Min. Hassan", "role":"Social Services Minister", "cluster":"social",
             "personality":"You are Social Services Minister protecting vulnerable populations. Protective, equity-focused. Reply in 2-3 sentences."},
            {"id":"social_deputy1", "name":"Dr. Patterson", "role":"Poverty & Equity", "cluster":"social",
             "personality":"You are poverty reduction chief. Data-driven on inequality. Reply in 2-3 sentences."},
            {"id":"social_deputy2", "name":"Ms. Müller", "role":"Regional Development", "cluster":"social",
             "personality":"You are regional development chief addressing geographic disparities. Place-based, community-focused. Reply in 2-3 sentences."},
            {"id":"finance_minister", "name":"Min. Sterling", "role":"Finance Minister", "cluster":"finance",
             "personality":"You are Finance Minister managing budget constraints and green financing. Conservative, strategic. Reply in 2-3 sentences."},
            {"id":"finance_deputy1", "name":"Dr. Chen", "role":"Budget Director", "cluster":"finance",
             "personality":"You are budget director allocating limited resources. Numbers-focused, trade-off aware. Reply in 2-3 sentences."},
            {"id":"finance_deputy2", "name":"Mr. O'Brien", "role":"Green Finance", "cluster":"finance",
             "personality":"You are green finance specialist mobilizing sustainable investment. Market-focused. Reply in 2-3 sentences."},
            {"id":"infra_minister", "name":"Min. DeMarco", "role":"Infrastructure Minister", "cluster":"infrastructure",
             "personality":"You are Infrastructure Minister coordinating projects and timelines. Project-manager, deadline-focused. Reply in 2-3 sentences."},
            {"id":"infra_deputy1", "name":"Eng. Robinson", "role":"Civil Engineering", "cluster":"infrastructure",
             "personality":"You are chief civil engineer. Design and safety-focused. Reply in 2-3 sentences."},
            {"id":"infra_deputy2", "name":"Dr. Walsh", "role":"Environmental Compliance", "cluster":"infrastructure",
             "personality":"You are environmental compliance officer on infrastructure projects. Regulatory, protective. Reply in 2-3 sentences."},
            {"id":"research_chief", "name":"Dr. Adenauer", "role":"Chief Scientist", "cluster":"executive",
             "personality":"You are chief scientist advising on research and innovation. Academic, evidence-based. Reply in 2-3 sentences."},
            {"id":"communications_director", "name":"Ms. Fraser", "role":"Government Communications", "cluster":"executive",
             "personality":"You are government communications director managing public narrative. Strategic, message-focused. Reply in 2-3 sentences."},
            {"id":"parliament_liaison", "name":"MP Thompson", "role":"Parliamentary Liaison", "cluster":"executive",
             "personality":"You are parliament liaison managing legislative support. Political, aware of constraints. Reply in 2-3 sentences."},
            {"id":"local_govt", "name":"Mayor Jackson", "role":"Local Government Rep", "cluster":"social",
             "personality":"You are city mayor representing local implementation challenges. Ground-level, pragmatic. Reply in 2-3 sentences."},
            {"id":"private_sector", "name":"CEO Fontana", "role":"Industry Council CEO", "cluster":"economy",
             "personality":"You are industry council CEO representing business interests. Profit-conscious, competitive. Reply in 2-3 sentences."},
            {"id":"ngo_advocate", "name":"Dr. Okoro", "role":"Civil Society Advocate", "cluster":"social",
             "personality":"You are NGO advocate pushing for social justice and environmental protection. Mission-driven. Reply in 2-3 sentences."},
        ]
    },

    # ══════════════════════════════════════════════════════════════════════════════
    # MULTI-DISTRICT PRESETS
    # ══════════════════════════════════════════════════════════════════════════════

    "tech_policy_districts": {
        "name": "Tech Innovation Hub + Policy District (2-District Demo)",
        "topic": "How should AI regulation balance innovation and public safety across sectors?",
        "mode": "conversation",
        "districts": {
            "tech_hub": {
                "label": "Tech Innovation Hub",
                "offset_x": 0,
                "offset_z": 0,
                "color_theme": "#2196F3",
                "clusters": {
                    "startups": {"label":"AI Startups",  "color":"#2196F3","cx":0,"cz":0},
                    "bigtech":  {"label":"Big Tech",     "color":"#1976D2","cx":0,"cz":0},
                },
                "agents": [
                    {"id":"elena_startup", "name":"Elena", "role":"AI Startup CEO", "cluster":"startups",
                     "personality":"You are Elena, CEO of an AI startup in Tech Hub. Innovation-focused. You can reach out to policy makers in Policy District when needed. Reply in 2-3 sentences."},
                    {"id":"dr_kim_ml", "name":"Dr. Kim", "role":"ML Researcher", "cluster":"bigtech",
                     "personality":"You are Dr. Kim, ML researcher at BigTech. Technical expert who follows policy discussions. You can share technical insights with Policy District. Reply in 2-3 sentences."},
                    {"id":"marcus_vc", "name":"Marcus", "role":"VC Investor", "cluster":"startups",
                     "personality":"You are Marcus, venture capitalist in Tech Hub. Market-focused, tracking regulatory changes from Policy District. Reply in 2-3 sentences."},
                ]
            },
            "policy_district": {
                "label": "Policy & Governance District",
                "offset_x": 120,
                "offset_z": 0,
                "color_theme": "#4CAF50",
                "clusters": {
                    "regulators": {"label":"Regulators",   "color":"#4CAF50","cx":0,"cz":0},
                    "advocacy":   {"label":"Advocacy",     "color":"#66BB6A","cx":0,"cz":0},
                },
                "agents": [
                    {"id":"sen_torres_reg", "name":"Sen. Torres", "role":"AI Regulator", "cluster":"regulators",
                     "personality":"You are Senator Torres in Policy District, focused on AI regulation. You monitor Tech Hub discussions and propose policies. You can ask tech leaders for input. Reply in 2-3 sentences."},
                    {"id":"maya_advocate", "name":"Maya", "role":"Public Advocate", "cluster":"advocacy",
                     "personality":"You are Maya, public interest advocate in Policy District. You bridge Tech Hub and Policy District to ensure public safety. Reply in 2-3 sentences."},
                    {"id":"prof_chen_legal", "name":"Prof. Chen", "role":"Tech Law Expert", "cluster":"regulators",
                     "personality":"You are Prof. Chen, technology law expert in Policy District. You translate between tech innovation and legal frameworks. Reply in 2-3 sentences."},
                ]
            }
        }
    },

    "multi_city_urban_planning": {
        "name": "Urban Planning: Tech City + Sustainable City (2-District Demo)",
        "topic": "How should cities balance smart technology development with sustainability goals?",
        "mode": "conversation",
        "districts": {
            "tech_city": {
                "label": "Smart Tech City",
                "offset_x": 0,
                "offset_z": 0,
                "color_theme": "#0ea5e9",
                "clusters": {
                    "tech_firms": {"label":"Tech Firms",   "color":"#0ea5e9","cx":0,"cz":0},
                    "developers": {"label":"Developers",   "color":"#0284c7","cx":0,"cz":0},
                },
                "agents": [
                    {"id":"cto_smart", "name":"Alex Chen", "role":"Tech City CTO", "cluster":"tech_firms",
                     "personality":"You are Alex, CTO of Smart Tech City. You promote IoT, AI, and digital infrastructure. You engage with Sustainable City on integration. Reply in 2-3 sentences."},
                    {"id":"dev_lead", "name":"Jordan Lee", "role":"Infrastructure Dev Lead", "cluster":"developers",
                     "personality":"You are Jordan, leading infrastructure development. You focus on connectivity and smart systems. Reply in 2-3 sentences."},
                    {"id":"investor_tech", "name":"Sarah Park", "role":"Tech Investor", "cluster":"tech_firms",
                     "personality":"You are Sarah, tech investor backing Smart City initiatives. Returns-focused but open to sustainability. Reply in 2-3 sentences."},
                ]
            },
            "sustainable_city": {
                "label": "Sustainable City Initiative",
                "offset_x": 120,
                "offset_z": 0,
                "color_theme": "#10b981",
                "clusters": {
                    "environment": {"label":"Environment", "color":"#10b981","cx":0,"cz":0},
                    "planners":    {"label":"Urban Planners", "color":"#059669","cx":0,"cz":0},
                },
                "agents": [
                    {"id":"env_director", "name":"Nina Okonkwo", "role":"Environmental Director", "cluster":"environment",
                     "personality":"You are Nina, environmental director of Sustainable City. You prioritize carbon neutrality and green spaces. You collaborate with Tech City. Reply in 2-3 sentences."},
                    {"id":"urban_planner", "name":"Marco Rossi", "role":"Urban Planner", "cluster":"planners",
                     "personality":"You are Marco, urban planner committed to livable, sustainable design. You seek tech solutions for urban challenges. Reply in 2-3 sentences."},
                    {"id":"community_lead", "name":"Amara Williams", "role":"Community Leader", "cluster":"environment",
                     "personality":"You are Amara, community leader advocating for local interests. You ensure sustainability serves residents. Reply in 2-3 sentences."},
                ]
            }
        }
    },
}


# -- FastAPI
from fastapi.encoders import jsonable_encoder
import json

app = FastAPI(title="Social Agents City v15")

# Force UTF-8 JSON encoding
class UTF8JSONResponse(JSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(content, ensure_ascii=False, allow_nan=False).encode('utf-8')
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    print(f"[ERROR] {request.url}: {exc}\n{tb}")
    return JSONResponse(status_code=500, content={"error": f"Server error: {str(exc)}"})

WORKSPACE.mkdir(parents=True, exist_ok=True)
if (WORKSPACE / "index.html").exists():
    app.mount("/static", StaticFiles(directory=str(WORKSPACE)), name="static")

@app.get("/", response_class=HTMLResponse)
async def root():
    p = Path("src/frontend/index.html")
    if p.exists():
        return p.read_text(encoding="utf-8")
    return "<h1>Social Agents City v24</h1><p>index.html not found at {}</p>".format(p.absolute())

@app.get("/voronoi_system.js")
async def serve_voronoi():
    p = Path("src/frontend/js/voronoi_system.js")
    if p.exists():
        return FileResponse(p, media_type="application/javascript")
    return {"error": "File not found"}

@app.get("/layout_system.js")
async def serve_layout():
    p = Path("src/frontend/js/layout_system.js")
    if p.exists():
        return FileResponse(p, media_type="application/javascript")
    return {"error": "File not found"}

@app.get("/voronoi_pure.js")
async def serve_voronoi_pure():
    p = Path("src/frontend/js/voronoi_system.js")
    if p.exists():
        return FileResponse(p, media_type="application/javascript")
    return {"error": "File not found"}

@app.get("/js/voronoi_system.js")
async def serve_voronoi_system():
    p = Path("src/frontend/js/voronoi_system.js")
    if p.exists():
        return FileResponse(p, media_type="application/javascript")
    return {"error": "File not found"}

@app.get("/js/area_manager.js")
async def serve_area_manager():
    p = Path("src/frontend/js/area_manager.js")
    if p.exists():
        return FileResponse(p, media_type="application/javascript")
    return {"error": "File not found"}

@app.get("/js/area_validator.js")
async def serve_area_validator():
    p = Path("src/frontend/js/area_validator.js")
    if p.exists():
        return FileResponse(p, media_type="application/javascript")
    return {"error": "File not found"}

@app.get("/test_voronoi.html")
async def serve_test():
    p = Path("test_voronoi.html")
    if p.exists():
        return FileResponse(p, media_type="text/html")
    return {"error": "File not found"}

@app.get("/debug.html")
async def serve_debug():
    p = Path("debug.html")
    if p.exists():
        return FileResponse(p, media_type="text/html")
    return {"error": "File not found"}

@app.get("/test_minimal.html")
async def serve_test_minimal():
    p = Path("test_minimal.html")
    if p.exists():
        return FileResponse(p, media_type="text/html")
    return {"error": "File not found"}

# -- Config
@app.post("/api/config")
async def set_config(body: dict):
    # Configurable fields
    string_fields = ("url","key","model","sentiment_model","mode")
    int_fields = ("context_window","agent_history","context_turns")
    bool_fields = ("ssl","include_topic","include_history","include_agent_name")

    for k in string_fields:
        if k in body:
            CFG[k] = body[k]

    for k in int_fields:
        if k in body:
            CFG[k] = max(1, int(body[k]))

    for k in bool_fields:
        if k in body:
            CFG[k] = bool(body[k])

    if "temperature" in body:
        CFG["temperature"] = max(0.0, min(2.0, float(body["temperature"])))

    return {"status":"ok","config":CFG}

@app.get("/api/config")
async def get_config():
    """Get current configuration"""
    return {"config": CFG}

@app.get("/api/models")
async def list_models():
    models, kind = get_models()
    if not models:
        return {"models":[], "error":"Could not reach LLM endpoint", "url": CFG["url"]}
    return {"models": models, "kind": kind}

# -- State (now includes emotions + files)
@app.get("/api/state")
async def get_state():
    # SECURITY: Log state access for debugging preset preloading issue
    print(f"[DEBUG] get_state() called: {len(agents)} agents, {len(CLUSTER_CONFIG)} clusters")
    if len(agents) > 0:
        print(f"[WARNING] Unexpected agents found: {list(agents.keys())}")

    # Convert any sets to lists for JSON serialization
    def convert_sets(obj):
        if isinstance(obj, set):
            return list(obj)
        elif isinstance(obj, dict):
            return {k: convert_sets(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_sets(item) for item in obj]
        return obj

    return UTF8JSONResponse({
        "agents": list(agents.values()),
        "cluster_colors": {k: v["color"] for k, v in CLUSTER_CONFIG.items()},
        "cluster_config": CLUSTER_CONFIG,
        "districts": DISTRICT_CONFIG,
        "agent_district_map": agent_district_map,
        "cross_district_messages": cross_district_messages[-50:] if cross_district_messages else [],
        "config": {
            "model": CFG["model"],
            "sentiment_model": CFG.get("sentiment_model","lexicon"),
            "mode": CFG["mode"],
            "temperature": CFG.get("temperature", 0.7),
        },
        "current_round": current_round,
        "total_messages": len(global_messages),
        "total_snapshots": len(snapshots),
        "emotions_detected": convert_sets(_global_emotions),
        "files_detected": convert_sets(_global_files),
        "presets": {k: {"name": v["name"], "mode": v.get("mode","conv."),
                        "agent_count": len(v.get("agents", [])) if "agents" in v else sum(len(d.get("agents", [])) for d in v.get("districts", {}).values()),
                        "cluster_count": len(v.get("clusters",{})) if "clusters" in v else sum(len(d.get("clusters",{})) for d in v.get("districts", {}).values()),
                        "district_count": len(v.get("districts", {})) if "districts" in v else 1} for k, v in PRESETS.items()},
    })

# -- Preset loading
@app.post("/api/preset/load")
async def load_preset(body: dict):
    global agents, sim_log, global_messages, current_round, CLUSTER_CONFIG, snapshots, _global_emotions, _global_files
    global DISTRICT_CONFIG, district_messages, cross_district_messages, agent_district_map

    pid = body.get("preset_id","")
    if pid not in PRESETS:
        return {"error": f"Unknown preset: {pid}"}

    p_raw = PRESETS[pid]
    # Normalize single-district presets to multi-district format
    p = _normalize_preset(p_raw)

    # Reset all state
    agents = {}
    CLUSTER_CONFIG = {}
    DISTRICT_CONFIG = {}
    agent_district_map = {}
    district_messages = {}
    cross_district_messages = []
    sim_log = []
    global_messages = []
    current_round = 0
    _global_emotions.clear()
    _global_files.clear()

    # Load districts and their contents
    for district_id, district_data in p["districts"].items():
        DISTRICT_CONFIG[district_id] = {
            "label": district_data.get("label", district_id),
            "offset_x": district_data.get("offset_x", 0),
            "offset_z": district_data.get("offset_z", 0),
            "color_theme": district_data.get("color_theme", "#8b5cf6")
        }

        # Load clusters with district prefix
        for cluster_id, cluster_data in district_data.get("clusters", {}).items():
            full_cluster_id = f"{district_id}_{cluster_id}"
            CLUSTER_CONFIG[full_cluster_id] = {
                **cluster_data,
                "district": district_id,
                "cx": cluster_data.get("cx", 0) + district_data.get("offset_x", 0),
                "cz": cluster_data.get("cz", 0) + district_data.get("offset_z", 0)
            }

        # Initialize district-local messages list
        district_messages[district_id] = []

        # Load agents
        for agent_data in district_data.get("agents", []):
            aid = agent_data["id"]
            full_cluster_id = f"{district_id}_{agent_data['cluster']}"
            agents[aid] = _fresh({
                **agent_data,
                "cluster": full_cluster_id,
                "district": district_id
            })
            agent_district_map[aid] = district_id

    if "mode" in p:
        CFG["mode"] = p["mode"]

    _auto_arrange_clusters()

    # Reset metrics engine
    try:
        metrics = get_metrics()
        metrics.reset_metrics()
    except Exception as e:
        print(f"⚠ Metrics reset error: {e}")

    # Build response with district info
    return {
        "status": "loaded",
        "agents": len(agents),
        "districts": len(DISTRICT_CONFIG),
        "topic": p.get("topic", ""),
        "districts_config": DISTRICT_CONFIG,
        "agent_district_map": agent_district_map
    }
    snapshots = []
    _global_emotions = {}
    _global_files = {}

    # === PHASE 1: RESET METRICS ON PRESET LOAD ===
    try:
        metrics = get_metrics()
        metrics.reset_metrics()
    except Exception as e:
        print(f"⚠ Metrics reset error: {e}")

    _auto_arrange_clusters()
    return {"status":"loaded", "agents":len(agents), "topic": p.get("topic",""),
            "clusters": CLUSTER_CONFIG}

# -- Analytics
def _build_analytics():
    total_turns = sum(a["turn_count"] for a in agents.values())
    total_tokens = sum(a["total_tokens"] for a in agents.values())
    total_cost = sum(a["total_cost_usd"] for a in agents.values())
    agent_stats = [{
        "id": a["id"], "name": a["name"], "role": a["role"],
        "cluster": a["cluster"], "model": a.get("model") or "(global)",
        "temperature": a.get("temperature") if a.get("temperature") is not None else "(global)",
        "turns": a["turn_count"], "words": a["word_count"], "tokens": a["total_tokens"],
        "cost_usd": a["total_cost_usd"], "avg_latency_ms": a["avg_latency_ms"],
        "valence": a["valence"], "arousal": a["arousal"], "dominance": a["dominance"],
        "influence": a["influence"],
        "interactions": sum(a.get("interactions",{}).values()),
        "allegation_count": a.get("allegation_count", 0),
        "argument_score": a.get("argument_score", 0),
        "emotions": a.get("detected_emotions", {}),
        "files": a.get("detected_files", {}),
    } for a in agents.values()]
    ranked = sorted(agent_stats, key=lambda x: x["influence"], reverse=True)
    for i, r in enumerate(ranked):
        r["rank"] = i + 1
    mention_matrix = {a["id"]: dict(a.get("mentions",{})) for a in agents.values()}
    interaction_matrix = {a["id"]: dict(a.get("interactions",{})) for a in agents.values()}
    by_cluster = {}
    for a in agents.values():
        cl = a["cluster"]
        if cl not in by_cluster:
            by_cluster[cl] = {"agents":0,"tokens":0,"cost":0.0,"turns":0,"avg_valence":0.0}
        by_cluster[cl]["agents"] += 1
        by_cluster[cl]["tokens"] += a["total_tokens"]
        by_cluster[cl]["cost"]   += a["total_cost_usd"]
        by_cluster[cl]["turns"]  += a["turn_count"]
        by_cluster[cl]["avg_valence"] += a["valence"]
    for cl in by_cluster:
        n = max(by_cluster[cl]["agents"], 1)
        by_cluster[cl]["avg_valence"] = round(by_cluster[cl]["avg_valence"] / n, 3)
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "sentiment_model": CFG.get("sentiment_model","lexicon"),
        "mode": CFG["mode"],
        "totals": {"agents": len(agents), "turns": total_turns,
                   "tokens": total_tokens, "cost_usd": round(total_cost, 6),
                   "log_entries": len(sim_log), "rounds": current_round},
        "by_agent": ranked,
        "by_cluster": by_cluster,
        "mention_matrix": mention_matrix,
        "interaction_matrix": interaction_matrix,
        "emotions_detected": _global_emotions,
        "files_detected": _global_files,
    }

@app.get("/api/analytics/export")
async def export_analytics():
    data = _build_analytics()
    # Convert any sets to lists for JSON serialization
    def convert_sets(obj):
        if isinstance(obj, set):
            return list(obj)
        elif isinstance(obj, dict):
            return {k: convert_sets(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_sets(item) for item in obj]
        return obj
    data = convert_sets(data)
    return JSONResponse(data)

# -- Agent CRUD
@app.post("/api/agent/add")
async def agent_add(body: dict):
    aid  = body.get("id","").strip().lower().replace(" ","_")
    name = body.get("name","").strip()
    if not aid or not name: return {"error":"id and name required"}
    if aid in agents:       return {"error":"Agent id already exists"}
    first_cluster = list(CLUSTER_CONFIG.keys())[0] if CLUSTER_CONFIG else "default"
    a = {"id":aid, "name":name,
         "role":        body.get("role","Custom"),
         "cluster":     body.get("cluster", first_cluster),
         "model":       body.get("model",""),
         "temperature": body.get("temperature", None),
         "personality": body.get("personality",f"You are {name}. Reply in 2-3 sentences."),
         "is_moderator": body.get("is_moderator", False)}
    agents[aid] = _fresh(a)
    if a["cluster"] not in CLUSTER_CONFIG:
        CLUSTER_CONFIG[a["cluster"]] = {"label": a["cluster"].title(), "color":"#8b5cf6","cx":0,"cz":0}
    _auto_arrange_clusters()
    return {"status":"created","agent":agents[aid],"clusters":CLUSTER_CONFIG}

@app.delete("/api/agent/{aid}")
async def agent_del(aid: str):
    if aid not in agents: return {"error":"Not found"}
    del agents[aid]
    for a in agents.values():
        a["interactions"].pop(aid, None)
        a["mentions"].pop(aid, None)
    _auto_arrange_clusters()
    return {"status":"deleted","id":aid,"clusters":CLUSTER_CONFIG}

@app.patch("/api/agent/{aid}")
async def agent_patch(aid: str, body: dict):
    if aid not in agents: return {"error":"Not found"}
    a = agents[aid]
    for k in ("name","role","cluster","model","personality","temperature","is_moderator"):
        if k in body:
            a[k] = body[k]
    if a.get("cluster") and a["cluster"] not in CLUSTER_CONFIG:
        CLUSTER_CONFIG[a["cluster"]] = {"label": a["cluster"].title(), "color":"#8b5cf6","cx":0,"cz":0}
    _auto_arrange_clusters()
    return {"status":"updated","agent":a,"clusters":CLUSTER_CONFIG}

# -- Cluster management
@app.post("/api/clusters")
async def set_clusters(body: dict):
    global CLUSTER_CONFIG
    CLUSTER_CONFIG = body
    return {"status":"ok","clusters":CLUSTER_CONFIG}

@app.post("/api/clusters/add")
async def add_cluster(body: dict):
    cid = body.get("id","").strip().lower().replace(" ","_")
    if not cid: return {"error":"Cluster ID required"}
    if cid in CLUSTER_CONFIG: return {"error":"Cluster already exists"}
    CLUSTER_CONFIG[cid] = {
        "label": body.get("label", cid.title()),
        "color": body.get("color", "#8b5cf6"),
        "cx": 0, "cz": 0
    }
    _auto_arrange_clusters()
    return {"status":"created","id":cid,"clusters":CLUSTER_CONFIG}

@app.post("/api/clusters/auto-arrange")
async def api_auto_arrange():
    _auto_arrange_clusters()
    return {"clusters": CLUSTER_CONFIG}


# ══════════════════════════════════════════════════════════════════════════════
# SIMULATION ENDPOINTS (with snapshot capture after every turn)
# ══════════════════════════════════════════════════════════════════════════════

async def _run_turn(speaker, listener, topic, turns, model, name_map, loop):
    """Execute a single turn for speaker, update state, take snapshot."""
    global current_round

    # Use district-aware context if districts are loaded
    if DISTRICT_CONFIG:
        shared_ctx = _build_district_aware_context(speaker["id"])
        msgs = [{"role":"system","content":_build_district_aware_system_prompt(speaker)}]
    else:
        shared_ctx = _build_shared_context(speaker["id"])
        msgs = [{"role":"system","content":_build_system_prompt(speaker)}]

    if shared_ctx:
        msgs.append({"role":"system","content":shared_ctx})

    # Build conversation prompt based on configuration
    prompt_parts = []

    # Include topic if configured
    if CFG.get("include_topic", True):
        prompt_parts.append(f"Topic: {topic}")

    # Include conversation history if configured
    if CFG.get("include_history", True):
        context_limit = CFG.get("context_turns", 5)
        recent_global = global_messages[-context_limit:] if global_messages else []

        if recent_global or prompt_parts:  # Only add header if there's content
            prompt_parts.append("\n--- Conversation History ---")
            for msg in recent_global:
                ts = msg.get("ts", "")[:19]
                agent_name = msg.get("agent_name", "Unknown")
                text = msg.get("text", "")
                prompt_parts.append(f"[{ts}] {agent_name}: {text}")
            prompt_parts.append("--- End History ---")

    # Include agent name instruction if configured
    if CFG.get("include_agent_name", True):
        prompt_parts.append(f"You are {speaker['name']}. Continue the discussion and respond to what others said.")

    prompt = "\n".join(prompt_parts)
    msgs.append({"role":"user","content":prompt})

    m = _get_model_for_agent(speaker, model)
    t = _get_temp_for_agent(speaker)
    try:
        reply, usage = await loop.run_in_executor(EXECUTOR, lambda m=m,msgs=msgs,t=t: ollama_chat(m, msgs, t))
    except Exception as e:
        return {"agent_id":speaker["id"],"name":speaker["name"],"error":str(e),
                "text":f"[Error: {str(e)}]","sentences":[],"valence":0,"arousal":0,
                "dominance":0,"tokens":0,"cost":0,"model":m,"temperature":t,"round":current_round}

    speaker["history"] += [{"role":"user","content":prompt},{"role":"assistant","content":reply}]
    sents, va, ar, dom, top_words, all_mentions = analyse_reply(reply, name_map)
    _upd(speaker["id"], reply, usage, va, ar, dom, sents, top_words, all_mentions)
    _log_interaction(speaker["id"], listener["id"], detect_mentions(reply, name_map))

    # Detect if this is a cross-district message
    is_cross, cross_refs = _detect_cross_district_message(speaker["id"], reply, name_map) if DISTRICT_CONFIG else (False, [])
    speaker_district = agent_district_map.get(speaker["id"])

    # Build message record
    msg_record = {
        "ts": datetime.utcnow().isoformat(), "agent_id": speaker["id"],
        "agent_name": speaker["name"], "role": speaker["role"],
        "text": reply, "mode": CFG["mode"], "round": current_round
    }

    # Add district info if available
    if speaker_district:
        msg_record["district"] = speaker_district
        msg_record["is_cross_district"] = is_cross
        if is_cross:
            msg_record["cross_district_refs"] = cross_refs

    global_messages.append(msg_record)

    # Store in district-local messages
    if speaker_district and speaker_district in district_messages:
        district_messages[speaker_district].append(msg_record)

    # Store in cross-district messages if applicable
    if is_cross and cross_refs:
        cross_district_messages.append(msg_record)

    # Take snapshot after this turn
    _take_snapshot(current_round, len(global_messages)-1, speaker["id"], reply)

    return {
        "agent_id": speaker["id"], "name": speaker["name"],
        "text": reply, "sentences": sents,
        "valence": va, "arousal": ar, "dominance": dom,
        "tokens": usage["total_tokens"], "cost": usage["cost_usd"],
        "model": m, "temperature": t, "round": current_round
    }


@app.post("/api/simulate/step")
async def step(body: dict):
    global current_round
    a_id  = body.get("agent_a");  b_id = body.get("agent_b")
    topic = body.get("topic","How should cities grow sustainably?")
    model = body.get("model", CFG["model"])
    if not model:          return {"error":"No model selected"}
    if not agents:         return {"error":"No agents loaded. Load a preset first."}
    if a_id == b_id:       return {"error":"Agent A and B must be different"}
    if a_id not in agents: return {"error":f"Agent {a_id} not found"}
    if b_id not in agents: return {"error":f"Agent {b_id} not found"}
    a, b = agents[a_id], agents[b_id]
    name_map = {ag["name"]: ag["id"] for ag in agents.values()}
    loop = asyncio.get_event_loop()
    current_round += 1
    turns = []

    for speaker, listener in [(a, b), (b, a)]:
        turn = await _run_turn(speaker, listener, topic, turns, model, name_map, loop)
        turns.append(turn)

    entry = {"ts": datetime.utcnow().isoformat(), "type": "step",
             "topic": topic, "model": model, "round": current_round, "turns": turns}
    sim_log.append(entry)
    return entry


@app.post("/api/simulate/round")
async def round_sim(body: dict):
    global current_round
    model = body.get("model", CFG["model"])
    topic = body.get("topic", "")
    pairs = body.get("pairs", 3)
    rounds = body.get("rounds", 1)
    if not model: return {"error": "No model selected"}
    if not agents: return {"error": "No agents loaded. Load a preset first."}

    import random
    all_entries = []
    ids = list(agents.keys())

    for rnd in range(rounds):
        current_round += 1
        random.shuffle(ids)
        rnd_pairs = []
        for i in range(0, len(ids)-1, 2):
            rnd_pairs.append((ids[i], ids[i+1]))
        if not rnd_pairs and len(ids) >= 2:
            rnd_pairs = [(ids[0], ids[1])]

        for a_id, b_id in rnd_pairs[:pairs]:
            try:
                result = await step({"agent_a": a_id, "agent_b": b_id, "topic": topic, "model": model})
                if "error" not in result:
                    all_entries.append(result)
                    current_round -= 1
            except Exception as e:
                all_entries.append({"error": str(e), "pair": [a_id, b_id]})
        current_round += 1

    return {"rounds": all_entries}


@app.post("/api/simulate/broadcast")
async def broadcast_sim(body: dict):
    global current_round
    model = body.get("model", CFG["model"])
    topic = body.get("topic", "")
    if not model: return {"error": "No model selected"}
    if not agents: return {"error": "No agents loaded. Load a preset first."}
    current_round += 1
    name_map = {ag["name"]: ag["id"] for ag in agents.values()}
    loop = asyncio.get_event_loop()
    turns = []

    for aid, agent in agents.items():
        shared_ctx = _build_shared_context(aid)
        msgs = [{"role":"system","content":_build_system_prompt(agent)}]
        if shared_ctx:
            msgs.append({"role":"system","content":shared_ctx})

        # === OPTIMIZACIÓN: Contexto eficiente (fix slowdown) ===
        # En lugar de usar toda la historia que crece O(n),
        # usar solo últimos 2-4 turnos para mantener velocidad constante
        # Round 1: ~50ms, Round 50: ~50ms (no degradation)
        context_limit = 4 if current_round > 10 else min(CFG.get("agent_history",20), len(agent["history"]))
        msgs += agent["history"][-context_limit:]

        if turns:
            prev_summary = " | ".join(f"{t['name']}: {t['text'][:150]}" for t in turns[-3:])
            prompt = f"Topic: {topic}\nRecent speakers said: {prev_summary}\nNow it's your turn."
        else:
            prompt = f"Topic: {topic}\nYou speak first. Share your thoughts."
        msgs.append({"role":"user","content":prompt})

        m = _get_model_for_agent(agent, model)
        t = _get_temp_for_agent(agent)
        try:
            reply, usage = await loop.run_in_executor(EXECUTOR, lambda m=m,msgs=msgs,t=t: ollama_chat(m, msgs, t))
        except Exception as e:
            turns.append({"agent_id":aid,"name":agent["name"],"error":str(e),
                          "text":f"[Error: {str(e)}]","sentences":[],"valence":0,"arousal":0,
                          "dominance":0,"tokens":0,"cost":0,"model":m,"temperature":t,"round":current_round})
            continue

        agent["history"] += [{"role":"user","content":prompt},{"role":"assistant","content":reply}]
        sents, va, ar, dom, top_words, all_mentions = analyse_reply(reply, name_map)
        _upd(aid, reply, usage, va, ar, dom, sents, top_words, all_mentions)
        mentioned = detect_mentions(reply, name_map)
        for other_id in agents:
            if other_id != aid:
                _log_interaction(aid, other_id, mentioned)
                break

        global_messages.append({
            "ts": datetime.utcnow().isoformat(), "agent_id": aid,
            "agent_name": agent["name"], "role": agent["role"],
            "text": reply, "mode": CFG["mode"], "round": current_round
        })

        _take_snapshot(current_round, len(global_messages)-1, aid, reply)

        turns.append({
            "agent_id": aid, "name": agent["name"],
            "text": reply, "sentences": sents,
            "valence": va, "arousal": ar, "dominance": dom,
            "tokens": usage["total_tokens"], "cost": usage["cost_usd"],
            "model": m, "temperature": t, "round": current_round
        })

    entry = {"ts":datetime.utcnow().isoformat(),"type":"broadcast",
             "topic":topic,"model":model,"round":current_round,"turns":turns}
    sim_log.append(entry)
    return entry


@app.post("/api/simulate/debate")
async def debate_sim(body: dict):
    global current_round
    model = body.get("model", CFG["model"])
    topic = body.get("topic", "")
    if not model: return {"error": "No model selected"}
    if not agents: return {"error": "No agents loaded. Load a preset first."}
    current_round += 1
    name_map = {ag["name"]: ag["id"] for ag in agents.values()}
    loop = asyncio.get_event_loop()
    turns = []

    sorted_agents = sorted(agents.values(), key=lambda a: (not a.get("is_moderator",False), a["id"]))

    for agent in sorted_agents:
        aid = agent["id"]
        shared_ctx = _build_shared_context(aid)
        msgs = [{"role":"system","content":_build_system_prompt(agent)}]
        if shared_ctx:
            msgs.append({"role":"system","content":shared_ctx})
        msgs += agent["history"][-CFG.get("agent_history",20):]

        if agent.get("is_moderator") and not turns:
            prompt = f"You are the moderator. Topic: {topic}\nOpen the debate and invite arguments."
        elif turns:
            prev = " | ".join(f"{t['name']}: {t['text'][:120]}" for t in turns[-3:])
            prompt = f"Topic: {topic}\nPrevious: {prev}\nYour turn to {'moderate' if agent.get('is_moderator') else 'argue'}."
        else:
            prompt = f"Topic: {topic}\nPresent your opening argument."
        msgs.append({"role":"user","content":prompt})

        m = _get_model_for_agent(agent, model)
        t = _get_temp_for_agent(agent)
        try:
            reply, usage = await loop.run_in_executor(EXECUTOR, lambda m=m,msgs=msgs,t=t: ollama_chat(m, msgs, t))
        except Exception as e:
            turns.append({"agent_id":aid,"name":agent["name"],"error":str(e),
                          "text":f"[Error: {str(e)}]","sentences":[],"valence":0,"arousal":0,
                          "dominance":0,"tokens":0,"cost":0,"model":m,"temperature":t,"round":current_round})
            continue

        agent["history"] += [{"role":"user","content":prompt},{"role":"assistant","content":reply}]
        sents, va, ar, dom, top_words, all_mentions = analyse_reply(reply, name_map)
        _upd(aid, reply, usage, va, ar, dom, sents, top_words, all_mentions)
        mentioned = detect_mentions(reply, name_map)
        for other_id in agents:
            if other_id != aid:
                _log_interaction(aid, other_id, mentioned)

        global_messages.append({
            "ts": datetime.utcnow().isoformat(), "agent_id": aid,
            "agent_name": agent["name"], "role": agent["role"],
            "text": reply, "mode": CFG["mode"], "round": current_round
        })

        _take_snapshot(current_round, len(global_messages)-1, aid, reply)

        turns.append({
            "agent_id": aid, "name": agent["name"],
            "text": reply, "sentences": sents,
            "valence": va, "arousal": ar, "dominance": dom,
            "tokens": usage["total_tokens"], "cost": usage["cost_usd"],
            "model": m, "temperature": t, "round": current_round,
            "role": agent["role"]
        })

    entry = {"ts":datetime.utcnow().isoformat(),"type":"debate",
             "topic":topic,"model":model,"round":current_round,"turns":turns}
    sim_log.append(entry)
    return entry


@app.post("/api/simulate/developer")
async def develop_sim(body: dict):
    global current_round
    model = body.get("model", CFG["model"])
    task = body.get("task", body.get("topic",""))
    if not model: return {"error": "No model selected"}
    if not agents: return {"error": "No agents loaded. Load a preset first."}
    current_round += 1
    name_map = {ag["name"]: ag["id"] for ag in agents.values()}
    loop = asyncio.get_event_loop()
    turns = []

    phases = ["planning", "implementation", "review"]
    for pi, phase in enumerate(phases):
        for agent in agents.values():
            aid = agent["id"]
            shared_ctx = _build_shared_context(aid)
            msgs = [{"role":"system","content":_build_system_prompt(agent)}]
            if shared_ctx:
                msgs.append({"role":"system","content":shared_ctx})
            msgs += agent["history"][-CFG.get("agent_history",20):]

            if phase == "planning":
                prompt = f"Task: {task}\nPhase: Planning. Propose your approach and design decisions."
            elif phase == "implementation":
                prompt = f"Task: {task}\nPhase: Implementation. Write code or detail your contribution."
            else:
                prompt = f"Task: {task}\nPhase: Review. Review what others have proposed and give feedback."
            if turns:
                recent = " | ".join(f"{t['name']}: {t['text'][:100]}" for t in turns[-3:])
                prompt += f"\nRecent: {recent}"
            msgs.append({"role":"user","content":prompt})

            m = _get_model_for_agent(agent, model)
            t = _get_temp_for_agent(agent)
            try:
                reply, usage = await loop.run_in_executor(EXECUTOR, lambda m=m,msgs=msgs,t=t: ollama_chat(m, msgs, t))
            except Exception as e:
                turns.append({"agent_id":aid,"name":agent["name"],"error":str(e),
                              "text":f"[Error: {str(e)}]","sentences":[],"valence":0,"arousal":0,
                              "dominance":0,"tokens":0,"cost":0,"model":m,"temperature":t,
                              "round":current_round,"phase":phase})
                continue

            agent["history"] += [{"role":"user","content":prompt},{"role":"assistant","content":reply}]
            sents, va, ar, dom, top_words, all_mentions = analyse_reply(reply, name_map)
            _upd(aid, reply, usage, va, ar, dom, sents, top_words, all_mentions)
            for oid in agents:
                if oid != aid:
                    _log_interaction(aid, oid, detect_mentions(reply, name_map))

            global_messages.append({
                "ts": datetime.utcnow().isoformat(), "agent_id": aid,
                "agent_name": agent["name"], "role": agent["role"],
                "text": reply, "mode": "developer", "round": current_round
            })

            _take_snapshot(current_round, len(global_messages)-1, aid, reply)

            turns.append({
                "agent_id": aid, "name": agent["name"],
                "text": reply, "sentences": sents,
                "valence": va, "arousal": ar, "dominance": dom,
                "tokens": usage["total_tokens"], "cost": usage["cost_usd"],
                "model": m, "temperature": t, "round": current_round, "phase": phase
            })

    entry = {"ts":datetime.utcnow().isoformat(),"type":"developer",
             "task":task,"model":model,"round":current_round,"turns":turns}
    sim_log.append(entry)
    return entry


@app.post("/api/simulate/multi-round")
async def multi_round(body: dict):
    global current_round
    model = body.get("model", CFG["model"])
    topic = body.get("topic", "")
    rounds_n = body.get("rounds", 3)
    stop_at = body.get("stop_at_round")
    round_mode = body.get("round_mode", "group_random")

    all_rounds = []
    for i in range(rounds_n):
        if stop_at and current_round >= stop_at:
            break
        try:
            if round_mode == "debate":
                r = await debate_sim({"model": model, "topic": topic})
            elif round_mode == "developer":
                r = await develop_sim({"model": model, "task": topic, "topic": topic})
            else:
                r = await broadcast_sim({"model": model, "topic": topic})
            all_rounds.append(r)
        except Exception as e:
            all_rounds.append({"error": str(e), "round_index": i})
    return {"rounds": all_rounds, "stopped_at_round": current_round}


# ══════════════════════════════════════════════════════════════════════════════
# MULTI-DISTRICT SIMULATION
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/simulate/multi-district")
async def simulate_multi_district(body: dict):
    """Run one round across all districts in parallel.

    All districts advance simultaneously, each agent speaks once.
    """
    global current_round
    model = body.get("model", CFG["model"])
    topic = body.get("topic", "")

    if not model:
        return {"error": "No model selected"}
    if not agents:
        return {"error": "No agents loaded. Load a preset first."}
    if not DISTRICT_CONFIG:
        return {"error": "No districts loaded. Load a multi-district preset first."}

    current_round += 1

    # Group agents by district
    by_district = {}
    for aid, agent in agents.items():
        district = agent_district_map.get(aid)
        if district not in by_district:
            by_district[district] = []
        by_district[district].append(agent)

    name_map = {ag["name"]: ag["id"] for ag in agents.values()}
    loop = asyncio.get_event_loop()

    # Execute all districts in parallel
    async def run_district(d_id, d_agents):
        """Run one round within a single district."""
        turns = []
        for agent in d_agents:
            turn = await _run_turn(agent, None, topic, turns, model, name_map, loop)
            turns.append(turn)
        return {d_id: turns}

    # Gather all district tasks
    tasks = [run_district(d_id, d_agents) for d_id, d_agents in by_district.items()]
    results = await asyncio.gather(*tasks)

    # Merge results
    district_results = {}
    for result in results:
        district_results.update(result)

    # Count cross-district messages in this round
    cross_count = sum(1 for m in cross_district_messages
                      if m.get("round") == current_round and m.get("is_cross_district"))

    entry = {
        "ts": datetime.utcnow().isoformat(),
        "type": "multi_district",
        "topic": topic,
        "model": model,
        "round": current_round,
        "districts": district_results,
        "cross_district_count": cross_count
    }

    sim_log.append(entry)
    return entry


@app.post("/api/districts/connect")
async def force_cross_district_connection(body: dict):
    """Force a cross-district conversation between specific agents.

    User selects Agent A from District X and Agent B from District Y.
    They have a brief exchange with cross-district awareness.
    """
    global current_round

    agent_a_id = body.get("agent_a")
    agent_b_id = body.get("agent_b")
    topic = body.get("topic", "Cross-district coordination")
    model = body.get("model", CFG["model"])

    if agent_a_id not in agents or agent_b_id not in agents:
        return {"error": "Invalid agent IDs"}

    district_a = agent_district_map.get(agent_a_id)
    district_b = agent_district_map.get(agent_b_id)

    if not district_a or not district_b or district_a == district_b:
        return {"error": "Agents must be from different districts"}

    agent_a = agents[agent_a_id]
    agent_b = agents[agent_b_id]
    name_map = {ag["name"]: ag["id"] for ag in agents.values()}
    loop = asyncio.get_event_loop()

    current_round += 1

    # Agent A reaches out
    prompt_a = f"""CROSS-DISTRICT MESSAGE:
You are reaching out to {agent_b['name']} from {DISTRICT_CONFIG[district_b]['label']}.
Topic: {topic}

Initiate the conversation and explain why you're reaching out across districts."""

    msgs_a = [
        {"role":"system","content":_build_district_aware_system_prompt(agent_a)},
        {"role":"user","content":prompt_a}
    ]

    try:
        reply_a, usage_a = await loop.run_in_executor(EXECUTOR,
            lambda: ollama_chat(model, msgs_a, CFG.get("temperature", 0.7)))
    except Exception as e:
        return {"error": f"Failed to get Agent A response: {str(e)}"}

    # Analyze Agent A's message
    sents_a, va_a, ar_a, dom_a, _, _ = analyse_reply(reply_a, name_map)
    _upd(agent_a_id, reply_a, usage_a, va_a, ar_a, dom_a, sents_a, [], [])

    # Store Agent A's message
    msg_a = {
        "ts": datetime.utcnow().isoformat(),
        "agent_id": agent_a_id,
        "agent_name": agent_a["name"],
        "role": agent_a["role"],
        "text": reply_a,
        "district": district_a,
        "is_cross_district": True,
        "target_agent": agent_b_id,
        "target_district": district_b,
        "round": current_round
    }

    global_messages.append(msg_a)
    district_messages.get(district_a, []).append(msg_a)
    cross_district_messages.append(msg_a)

    # Agent B responds
    prompt_b = f"""CROSS-DISTRICT MESSAGE - RESPONSE:
{agent_a['name']} from {DISTRICT_CONFIG[district_a]['label']} says:
"{reply_a}"

Respond to this cross-district message. Topic: {topic}"""

    msgs_b = [
        {"role":"system","content":_build_district_aware_system_prompt(agent_b)},
        {"role":"user","content":prompt_b}
    ]

    try:
        reply_b, usage_b = await loop.run_in_executor(EXECUTOR,
            lambda: ollama_chat(model, msgs_b, CFG.get("temperature", 0.7)))
    except Exception as e:
        return {"error": f"Failed to get Agent B response: {str(e)}"}

    # Analyze Agent B's message
    sents_b, va_b, ar_b, dom_b, _, _ = analyse_reply(reply_b, name_map)
    _upd(agent_b_id, reply_b, usage_b, va_b, ar_b, dom_b, sents_b, [], [])

    # Store Agent B's message
    msg_b = {
        "ts": datetime.utcnow().isoformat(),
        "agent_id": agent_b_id,
        "agent_name": agent_b["name"],
        "role": agent_b["role"],
        "text": reply_b,
        "district": district_b,
        "is_cross_district": True,
        "responding_to": agent_a_id,
        "from_district": district_a,
        "round": current_round
    }

    global_messages.append(msg_b)
    district_messages.get(district_b, []).append(msg_b)
    cross_district_messages.append(msg_b)

    # Take snapshots
    _take_snapshot(current_round, len(global_messages)-2, agent_a_id, reply_a)
    _take_snapshot(current_round, len(global_messages)-1, agent_b_id, reply_b)

    return {
        "status": "connected",
        "round": current_round,
        "district_a": district_a,
        "district_b": district_b,
        "exchange": [
            {"agent": agent_a["name"], "text": reply_a, "district": district_a},
            {"agent": agent_b["name"], "text": reply_b, "district": district_b}
        ]
    }


# ══════════════════════════════════════════════════════════════════════════════
# TIMELINE + SNAPSHOTS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/timeline")
async def get_timeline():
    by_round = {}
    for msg in global_messages:
        r = msg.get("round", 0)
        if r not in by_round:
            by_round[r] = []
        by_round[r].append(msg)
    return {
        "total_rounds": current_round,
        "total_messages": len(global_messages),
        "total_snapshots": len(snapshots),
        "rounds": {str(k): v for k, v in sorted(by_round.items())}
    }

@app.get("/api/timeline/round/{round_num}")
async def get_round_timeline(round_num: int):
    msgs = [m for m in global_messages if m.get("round") == round_num]
    return {"round": round_num, "messages": msgs, "count": len(msgs)}

@app.get("/api/snapshots")
async def get_snapshots():
    """Return snapshot index (without full agent data, for timeline slider)."""
    index = []
    for i, s in enumerate(snapshots):
        index.append({
            "index": i,
            "round": s["round"],
            "msg_index": s["msg_index"],
            "ts": s["ts"],
            "trigger_agent": s["trigger_agent"],
            "emotion_count": len(s.get("emotions_active", {})),
            "file_count": len(s.get("files_active", {})),
        })
    return {"total": len(snapshots), "snapshots": index}

@app.get("/api/snapshot/{snap_index}")
async def get_snapshot(snap_index: int):
    """Return full snapshot data for timeline scrubbing."""
    if snap_index < 0 or snap_index >= len(snapshots):
        return {"error": "Snapshot index out of range", "total": len(snapshots)}
    return snapshots[snap_index]


# -- Problem I/O
@app.get("/api/problem/export")
async def export_problem():
    return JSONResponse({
        "topic": "",
        "mode": CFG["mode"],
        "temperature": CFG.get("temperature", 0.7),
        "clusters": CLUSTER_CONFIG,
        "agents": [{
            "id": a["id"], "name": a["name"], "role": a["role"],
            "cluster": a["cluster"], "personality": a["personality"],
            "model": a.get("model",""), "temperature": a.get("temperature"),
            "is_moderator": a.get("is_moderator", False)
        } for a in agents.values()]
    })

@app.post("/api/problem/load")
async def load_problem(body: dict):
    global agents, sim_log, global_messages, current_round, CLUSTER_CONFIG, snapshots, _global_emotions, _global_files
    CLUSTER_CONFIG = {k: dict(v) for k, v in body.get("clusters",{}).items()}
    agent_list = body.get("agents",[])
    agents = {a["id"]: _fresh(a) for a in agent_list}
    if "mode" in body: CFG["mode"] = body["mode"]
    if "temperature" in body: CFG["temperature"] = float(body["temperature"])
    sim_log = []
    global_messages = []
    current_round = 0
    snapshots = []
    _global_emotions = {}
    _global_files = {}
    _auto_arrange_clusters()
    return {"status":"loaded","agents":len(agents),"clusters":CLUSTER_CONFIG}

@app.get("/api/results/export")
async def export_results():
    return JSONResponse({
        "analytics": _build_analytics(),
        "log": sim_log[-200:],
        "global_messages": global_messages[-500:],
        "snapshots": snapshots[-500:],
    })

@app.post("/api/results/load")
async def load_results(body: dict):
    global sim_log, global_messages, snapshots
    sim_log = body.get("log", [])
    global_messages = body.get("global_messages", [])
    snapshots = body.get("snapshots", [])
    return {"status":"loaded","log_entries":len(sim_log),"messages":len(global_messages),"snapshots":len(snapshots)}

@app.post("/api/reset")
async def reset():
    global agents, sim_log, global_messages, current_round, CLUSTER_CONFIG, snapshots, _global_emotions, _global_files
    agents = {}
    sim_log = []
    global_messages = []
    current_round = 0
    CLUSTER_CONFIG = {}
    snapshots = []
    _global_emotions = {}
    _global_files = {}
    return {"status":"reset"}

@app.get("/api/log/export")
async def export_log():
    return JSONResponse(sim_log)


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1: METRICS ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/settings/preset")
async def switch_preset(body: dict):
    """Switch metrics preset configuration.

    Body: {"preset": "default" | "sensitive" | "stable" | "realtime"}
    """
    preset_name = body.get("preset", "default")

    try:
        metrics = get_metrics()
        metrics.set_preset(preset_name)
        return {
            "success": True,
            "preset": preset_name,
            "message": f"Switched to {preset_name} preset. Metrics will use new sensitivity."
        }
    except Exception as e:
        return {"error": str(e), "success": False}


@app.get("/api/metrics/status/{agent_id}")
async def get_metrics_status(agent_id: str):
    """Get current metric status for an agent.

    Returns: {
        "influence": {"smoothed": 0.75, "variance": 0.05, "trend": 1},
        "arousal": {...},
        ...
    }
    """
    if agent_id not in agents:
        return {"error": f"Agent {agent_id} not found"}

    try:
        metrics = get_metrics()
        return metrics.get_metric_status(agent_id)
    except Exception as e:
        return {"error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    # ═══════════════════════════════════════════════════════════════════════
    # SECURITY: Enforce empty state on startup - NO PRESET PRELOADING
    # ═══════════════════════════════════════════════════════════════════════
    agents = {}
    CLUSTER_CONFIG = {}
    sim_log = []
    global_messages = []
    snapshots = []
    current_round = 0
    _global_emotions = {}
    _global_files = set()

    print(f"\n  Social Agents City v15")
    print(f"  http://localhost:{PORT}\n")
    print(f"  ✓ Security check: State forcibly cleared")
    print(f"  ✓ Agents: {len(agents)} (must be 0)")
    print(f"  ✓ Clusters: {len(CLUSTER_CONFIG)} (must be 0)")
    print(f"  No agents loaded at boot. Load a preset to start.\n")

    # Force UTF-8 encoding
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    uvicorn.run(app, host="0.0.0.0", port=PORT, env_file=None, timeout_keep_alive=300)
