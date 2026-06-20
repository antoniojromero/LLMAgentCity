"""Server configuration and constants."""

# Server settings
PORT = 8002
HOST = "0.0.0.0"

# Simulation settings
DEFAULT_ROUNDS = 1
MAX_ROUNDS = 20
DEFAULT_MODE = "conversation"

# Metric scaling
METRIC_SCALING = {
    "influence": 8.0,
    "tokens": 10.0,
    "valence": 2.0,
    "arousal": 2.0,
    "dominance": 2.0,
    "latency": 5000.0,
}

# Building constraints
MIN_HEIGHT = 0.3
MAX_HEIGHT = 6.0
MIN_WIDTH = 0.5
MAX_WIDTH = 2.0

# Layout settings
PLOT = 7.0
AGENT_GAP = 0.4
CGAP = 3.5
BUILDING_PAD = 0.07

# Emotion thresholds
EMOTION_DETECTION_THRESHOLD = 1
EMOTION_COLORS = {
    "joy": "#fbbf24",
    "sadness": "#3b82f6",
    "anger": "#ef4444",
    "fear": "#8b5cf6",
    "surprise": "#f97316",
    "trust": "#22c55e",
    "disgust": "#84cc16",
    "anticipation": "#06b6d4",
}

# Lexicon path
LEXICON_PATH = "../data/lexicons/emotions_compiled.csv"

# Presets path
PRESETS_PATH = "../data/presets/"
