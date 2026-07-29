"""
Emotion Engine - Loads NRC Emotion Lexicon and GoEmotions mapping
for word-level emotion detection and coloring.

NRC Lexicon: 14,182 words × 8 emotions (anger, fear, anticipation, trust,
  surprise, sadness, joy, disgust) + 2 sentiments (positive, negative)
GoEmotions: 27 emotions mapped to 6 Ekman categories
"""

import re
import csv
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

NRC_EMOTIONS = ["anger", "anticipation", "disgust", "fear", "joy", "sadness", "surprise", "trust"]

EMOTION_COLORS_HEX = {
    "anger": "#ef4444",
    "fear": "#8b5cf6",
    "disgust": "#84cc16",
    "joy": "#fbbf24",
    "sadness": "#3b82f6",
    "surprise": "#f97316",
    "trust": "#22c55e",
    "anticipation": "#06b6d4",
    "love": "#f472b6",
    "optimism": "#34d399",
    "approval": "#38bdf8",
    "admiration": "#a78bfa",
    "amusement": "#fbbf24",
    "excitement": "#f59e0b",
    "gratitude": "#4ade80",
    "pride": "#c084fc",
    "relief": "#6ee7b7",
    "caring": "#fb7185",
    "desire": "#e11d48",
    "curiosity": "#2dd4bf",
    "confusion": "#a3a3a3",
    "realization": "#818cf8",
    "annoyance": "#f97316",
    "disappointment": "#64748b",
    "disapproval": "#dc2626",
    "embarrassment": "#f43f5e",
    "grief": "#1e40af",
    "nervousness": "#c084fc",
    "remorse": "#475569",
    "neutral": "#94a3b8",
}


class EmotionEngine:
    """Word-level emotion detection using NRC Emotion Lexicon."""

    def __init__(self, lexicon_dir: Path = None):
        self.word_emotions: dict = defaultdict(dict)
        self.word_sentiment: dict = {}
        self.nrc_words: dict = {}
        self.vad_lexicon: dict = {}
        self.ekman_map: dict = {}
        self.goemotions_ekman: dict = {}
        self._loaded = False

        if lexicon_dir is None:
            base = Path(__file__).parent.parent.parent
            lexicon_dir = base / "data" / "lexicons" / "external"

        self.lexicon_dir = Path(lexicon_dir)

    def load_all(self) -> bool:
        """Load all available lexicons."""
        loaded = False
        loaded |= self._load_nrc()
        loaded |= self._load_goemotions_mappings()
        loaded |= self._load_vad()
        self._loaded = loaded
        return loaded

    def _load_nrc(self) -> bool:
        """Load the NRC Emotion Lexicon."""
        nrc_path = self.lexicon_dir / "NRC-emotion-lexicon-wordlevel-alphabetized-v0.92.txt"
        if not nrc_path.exists():
            return False

        with open(nrc_path, "r", encoding="utf-8") as f:
            line_count = 0
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) != 3:
                    continue
                word, emotion, flag = parts
                word = word.lower()
                flag = int(flag)

                self.nrc_words[word] = self.nrc_words.get(word, {})
                self.nrc_words[word][emotion] = flag
                line_count += 1

                if flag == 1:
                    if emotion in NRC_EMOTIONS:
                        self.word_emotions[word][emotion] = self.word_emotions[word].get(emotion, 0) + 1
                    elif emotion == "positive":
                        self.word_sentiment[word] = "positive"
                    elif emotion == "negative":
                        self.word_sentiment[word] = "negative"

        n_words = len(self.nrc_words)
        n_emotion_words = len(self.word_emotions)
        # Build ekman map locally from NRC
        self._build_ekman_mapping()

        return True

    def _build_ekman_mapping(self):
        """Map NRC 8 emotions to colors (already defined in EMOTION_COLORS_HEX)."""
        pass

    def _load_vad(self) -> bool:
        """Load VAD lexicon (Valence, Arousal, Dominance) via Russell's circumplex."""
        vad_path = self.lexicon_dir.parent / "vad_lexicon.csv"
        if not vad_path.exists():
            return False
        with open(vad_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                self.vad_lexicon[row["word"].lower()] = (
                    float(row["valence"]), float(row["arousal"]), float(row["dominance"])
                )
        return len(self.vad_lexicon) > 0

    def pad_vad(self, text: str) -> tuple:
        """Compute Valence, Arousal, Dominance for a text using VAD lexicon."""
        words = re.findall(r"[a-z']+", text.lower())
        v_sum, a_sum, d_sum = 0, 0, 0
        count = 0
        for w in words:
            if w in self.vad_lexicon:
                v, a, d = self.vad_lexicon[w]
                v_sum += v; a_sum += a; d_sum += d
                count += 1
        if count == 0:
            return 0, 0, 0
        return round(v_sum / count, 3), round(a_sum / count, 3), round(d_sum / count, 3)

    def _load_goemotions_mappings(self) -> bool:
        """Load GoEmotions mapping files."""
        import json

        ekman_path = self.lexicon_dir / "ekman_mapping.json"
        sent_path = self.lexicon_dir / "sentiment_mapping.json"

        loaded = False
        if ekman_path.exists():
            with open(ekman_path) as f:
                self.goemotions_ekman = json.load(f)
            loaded = True

        if sent_path.exists():
            with open(sent_path) as f:
                self.goemotions_sentiment = json.load(f)
            loaded = True

        return loaded

    def get_word_emotion(self, word: str) -> dict:
        """
        Get emotion info for a word.
        Returns dict with 'word', 'emotion', 'color' or None if no emotion detected.
        """
        w = word.lower().strip(".,;:!?()[]{}\"'")
        if not w:
            return None

        if w in self.word_emotions:
            emotions = self.word_emotions[w]
            if emotions:
                primary = max(emotions, key=emotions.get)
                return {
                    "word": word,
                    "emotion": primary,
                    "color": EMOTION_COLORS_HEX.get(primary, "#fbbf24"),
                    "all_emotions": dict(emotions),
                }

        return None

    def analyze_text(self, text: str) -> Tuple[List[dict], float, float, float]:
        """
        Analyze text with word-level emotion detection.
        Returns (words_emotions, avg_valence, avg_arousal, avg_dominance).
        """
        words = re.findall(r'\b\w+\b', text)
        words_emotions = []
        v_sum, a_sum, d_sum = 0.0, 0.0, 0.0

        for word in words:
            emotion_data = self.get_word_emotion(word)
            if emotion_data:
                words_emotions.append({
                    "word": word,
                    "emotion": emotion_data["emotion"]
                })

        return words_emotions, 0, 0, 0

    def get_emotion_counts(self, text: str) -> dict:
        """Count emotions present in a text."""
        words = re.findall(r'\b\w+\b', text)
        counts = defaultdict(int)
        for word in words:
            result = self.get_word_emotion(word)
            if result:
                counts[result["emotion"]] += 1
        return dict(counts)

    def get_dominant_emotion(self, text: str) -> Tuple[str, str]:
        """Get dominant emotion and its hex color for a text."""
        counts = self.get_emotion_counts(text)
        if not counts:
            return ("neutral", EMOTION_COLORS_HEX["neutral"])
        dominant = max(counts, key=counts.get)
        return (dominant, EMOTION_COLORS_HEX.get(dominant, "#94a3b8"))

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def word_count(self) -> int:
        return len(self.nrc_words)

    @property
    def emotion_word_count(self) -> int:
        return len(self.word_emotions)


def get_emotion_engine() -> EmotionEngine:
    """Get or create singleton EmotionEngine."""
    global _engine
    if _engine is None:
        _engine = EmotionEngine()
        _engine.load_all()
    return _engine


def get_word_emotion(word: str) -> dict:
    return get_emotion_engine().get_word_emotion(word)


_engine: EmotionEngine = None