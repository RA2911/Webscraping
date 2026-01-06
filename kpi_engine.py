from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from sklearn.feature_extraction.text import TfidfVectorizer


analyzer = SentimentIntensityAnalyzer()


def split_into_sentences(text: str) -> List[str]:
    # simple splitter (fast + robust enough)
    text = (text or "").replace("\n", " ")
    parts = [p.strip() for p in text.split(".") if p.strip()]
    return parts


def compute_sentiment_kpis(text: str) -> Dict:
    """
    Returns:
      - sentence-level scores
      - aggregate KPIs
    """
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

    for s in sents[:2000]:  # safety cap
        sc = analyzer.polarity_scores(s)
        compound = sc["compound"]
        scores.append({"text": s, "compound": compound, "pos": sc["pos"], "neg": sc["neg"], "neu": sc["neu"]})

        # simple label thresholds
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
    """
    Lightweight topic proxy: TF-IDF top terms across corpus.
    """
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
    # sum tfidf across docs
    scores = np.asarray(X.sum(axis=0)).ravel()
    terms = vec.get_feature_names_out()
    pairs = list(zip(terms, scores))
    pairs.sort(key=lambda x: x[1], reverse=True)
    return [(t, float(s)) for t, s in pairs[:top_k]]


def overall_sentiment_rate(avg_compound: float, positivity_ratio: float, negativity_rate: float, intensity_index: float) -> float:
    """
    Composite score in [0..100] derived from other KPIs.
    """
    # normalize compound [-1..1] => [0..1]
    c = (avg_compound + 1.0) / 2.0
    # penalize negativity and high intensity when negative dominates
    neg_penalty = negativity_rate
    # intensity affects risk; we dampen impact by making it bounded
    intensity = min(1.0, max(0.0, intensity_index))  # approx [0..1]

    # weights (tunable)
    score01 = (
        0.45 * c +
        0.30 * positivity_ratio +
        0.25 * (1.0 - neg_penalty) -
        0.10 * intensity
    )
    score01 = max(0.0, min(1.0, score01))
    return round(score01 * 100.0, 2)


def build_dashboard_payload(company: str, corpus_texts: List[str]) -> Dict:
    merged = "\n\n".join(corpus_texts)

    sk = compute_sentiment_kpis(merged)
    topics = top_topics_keywords(corpus_texts, top_k=12)

    rate = overall_sentiment_rate(
        avg_compound=sk["avg_compound"],
        positivity_ratio=sk["positivity_ratio"],
        negativity_rate=sk["negativity_rate"],
        intensity_index=sk["intensity_index"]
    )

    # evidence snippets
    sents = sk["sentences"]
    most_neg = sorted(sents, key=lambda x: x["compound"])[:5]
    most_pos = sorted(sents, key=lambda x: x["compound"], reverse=True)[:5]

    # 7 master KPI cards + sub KPIs
    masters = {
        "Core Sentiment": {
            "avg_compound": sk["avg_compound"],
            "overall_sentiment_rate": rate,
        },
        "Positivity": {
            "positivity_ratio": round(sk["positivity_ratio"] * 100, 2),
        },
        "Negativity": {
            "negativity_rate": round(sk["negativity_rate"] * 100, 2),
        },
        "Intensity & Risk": {
            "intensity_index": round(sk["intensity_index"], 4),
        },
        "Topics & Aspects": {
            "top_topics": [{"term": t, "score": s} for t, s in topics],
        },
        "Volume & Coverage": {
            "sources_count": len(corpus_texts),
            "sentences_scanned": len(sk["sentences"]),
        },
        "Predictive Analysis": {
            "status": "ready"  # computed via ChatGPT on-demand
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
