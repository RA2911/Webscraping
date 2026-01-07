from __future__ import annotations

import re
from typing import Dict, List, Tuple

import numpy as np
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from sklearn.feature_extraction.text import TfidfVectorizer


analyzer = SentimentIntensityAnalyzer()

_STOP = {
    "the","and","for","with","that","this","from","are","was","were","have","has","had","will",
    "you","your","they","their","them","our","but","not","can","could","should","would","about",
    "into","over","under","more","most","very","than","then","when","what","which","who","why",
}


def split_into_sentences(text: str) -> List[str]:
    text = (text or "").replace("\n", " ")
    parts = [p.strip() for p in text.split(".") if p.strip()]
    return parts


def compute_sentiment_kpis(text: str) -> Dict:
    sents = split_into_sentences(text)
    if not sents:
        return {
            "sentences": [],
            "avg_compound": 0.0,
            "positivity_ratio": 0.0,
            "negativity_rate": 0.0,
            "neutrality_rate": 0.0,
            "intensity_index": 0.0,
        }

    scores = []
    pos = neg = neu = 0
    intensity_acc = 0.0

    for s in sents[:2000]:
        sc = analyzer.polarity_scores(s)
        compound = sc["compound"]
        scores.append({"text": s, "compound": compound, "pos": sc["pos"], "neg": sc["neg"], "neu": sc["neu"]})

        if compound >= 0.05:
            pos += 1
        elif compound <= -0.05:
            neg += 1
        else:
            neu += 1

        intensity_acc += abs(compound)

    n = len(scores)
    avg_compound = float(np.mean([x["compound"] for x in scores])) if n else 0.0
    positivity_ratio = pos / n if n else 0.0
    negativity_rate = neg / n if n else 0.0
    neutrality_rate = neu / n if n else 0.0
    intensity_index = intensity_acc / n if n else 0.0

    return {
        "sentences": scores,
        "avg_compound": avg_compound,
        "positivity_ratio": positivity_ratio,
        "negativity_rate": negativity_rate,
        "neutrality_rate": neutrality_rate,
        "intensity_index": intensity_index,
    }


def top_topics_keywords(texts: List[str], top_k: int = 12) -> List[Tuple[str, float]]:
    corpus = [t for t in texts if t and len(t) > 50]
    if len(corpus) < 1:
        return []

    vec = TfidfVectorizer(
        stop_words="english",
        max_features=3000,
        ngram_range=(1, 2),
        min_df=1
    )
    X = vec.fit_transform(corpus)
    scores = np.asarray(X.sum(axis=0)).ravel()
    terms = vec.get_feature_names_out()
    pairs = list(zip(terms, scores))
    pairs.sort(key=lambda x: x[1], reverse=True)
    return [(t, float(s)) for t, s in pairs[:top_k]]


def most_cited_words(text: str, top_k: int = 20, min_len: int = 5) -> List[Dict]:
    t = (text or "").lower()
    t = re.sub(r"[^a-z0-9\s]+", " ", t)
    words = [w for w in t.split() if len(w) >= min_len and w not in _STOP and not w.isdigit()]
    if not words:
        return []
    freq: Dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    items = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:top_k]
    return [{"word": w, "count": int(c)} for w, c in items]


def overall_sentiment_rate(avg_compound: float, positivity_ratio: float, negativity_rate: float, intensity_index: float) -> float:
    c = (avg_compound + 1.0) / 2.0
    neg_penalty = negativity_rate
    intensity = min(1.0, max(0.0, intensity_index))

    score01 = (
        0.45 * c +
        0.30 * positivity_ratio +
        0.25 * (1.0 - neg_penalty) -
        0.10 * intensity
    )
    score01 = max(0.0, min(1.0, score01))
    return round(score01 * 100.0, 2)


def build_dashboard_payload(company: str, corpus_texts: List[str], blocked_meta: List[Dict]) -> Dict:
    merged = "\n\n".join(corpus_texts)

    sk = compute_sentiment_kpis(merged)
    topics = top_topics_keywords(corpus_texts, top_k=12)
    words = most_cited_words(merged, top_k=20, min_len=5)

    rate = overall_sentiment_rate(
        avg_compound=sk["avg_compound"],
        positivity_ratio=sk["positivity_ratio"],
        negativity_rate=sk["negativity_rate"],
        intensity_index=sk["intensity_index"]
    )

    sents = sk["sentences"]
    most_neg = sorted(sents, key=lambda x: x["compound"])[:5]
    most_pos = sorted(sents, key=lambda x: x["compound"], reverse=True)[:5]

    # Short interpretations (shown in modal)
    interpretations = {
        "avg_compound": "Average sentiment tone (-1 very negative to +1 very positive).",
        "overall_sentiment_rate": "Composite score (0–100). Higher = healthier public sentiment.",
        "positivity_ratio": "Share of positive sentences (>= +0.05).",
        "negativity_rate": "Share of negative sentences (<= -0.05).",
        "neutrality_rate": "Share of neutral sentences.",
        "intensity_index": "Average emotional strength (higher = stronger emotions, risk if negative).",
    }

    masters = {
        "Core Sentiment": {
            "avg_compound": sk["avg_compound"],
            "overall_sentiment_rate": rate,
            "_help": {
                "avg_compound": interpretations["avg_compound"],
                "overall_sentiment_rate": interpretations["overall_sentiment_rate"],
            }
        },
        "Positivity": {
            "positivity_ratio": round(sk["positivity_ratio"] * 100, 2),
            "_help": {"positivity_ratio": interpretations["positivity_ratio"]}
        },
        "Negativity": {
            "negativity_rate": round(sk["negativity_rate"] * 100, 2),
            "_help": {"negativity_rate": interpretations["negativity_rate"]}
        },
        "Intensity & Risk": {
            "intensity_index": round(sk["intensity_index"], 4),
            "_help": {"intensity_index": interpretations["intensity_index"]}
        },
        "Topics & Aspects": {
            "top_topics": [{"term": t, "score": s} for t, s in topics],
        },
        "Most Cited Words": {
            "top_words": words
        },
        "Volume & Coverage": {
            "sources_ok": len(corpus_texts),
            "sources_blocked": len([m for m in blocked_meta if m.get("blocked")]),
            "blocked_list": blocked_meta[:30],
            "sentences_scanned": len(sk["sentences"]),
        },
        "Predictive Analysis": {
            "status": "ready"
        }
    }

    return {
        "company": company,
        "masters": masters,
        "overall_sentiment_rate": rate,
        "series": {
            "sentiment_distribution": {
                "pos": round(sk["positivity_ratio"] * 100, 2),
                "neg": round(sk["negativity_rate"] * 100, 2),
                "neu": round(sk["neutrality_rate"] * 100, 2),
            }
        },
        "evidence": {
            "most_negative": most_neg,
            "most_positive": most_pos
        }
    }
