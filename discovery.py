import json
import os
import re
from typing import List, Dict

from openai import OpenAI


_BAD_KEYWORDS = {
    "massage", "spa", "salon", "escort", "adult", "dating", "hotel deal", "coupon"
}


def _extract_urls(text: str) -> List[str]:
    urls = re.findall(r"https?://[^\s\]\)\"'>]+", text or "")
    out = []
    seen = set()
    for u in urls:
        u2 = u.rstrip(".,;:!?)\"]'")
        if u2 not in seen:
            out.append(u2)
            seen.add(u2)
    return out


def _norm_tokens(s: str) -> List[str]:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9\s]+", " ", s)
    toks = [t for t in s.split() if len(t) >= 3]
    return toks


def _is_relevant_url(company: str, hints: str, url: str, reason: str = "") -> bool:
    u = (url or "").lower()
    r = (reason or "").lower()

    # Hard reject obvious garbage
    for bad in _BAD_KEYWORDS:
        if bad in u or bad in r:
            return False

    # Must contain at least one meaningful token from company/hints (loose but effective)
    comp_toks = set(_norm_tokens(company))
    hint_toks = set(_norm_tokens(hints))
    keep_toks = {t for t in (comp_toks | hint_toks) if t not in {"the", "and", "for", "with", "dubai"}}

    # If no tokens (edge case), allow
    if not keep_toks:
        return True

    # check url string + reason text
    hay = u + " " + r
    hits = sum(1 for t in keep_toks if t in hay)
    return hits >= 1


def discover_comment_links(company: str, max_links: int = 12, hints: str = "") -> List[Dict]:
    """
    Returns list of dicts:
      [{"url": "...", "reason": "...", "confidence": 0-100}]
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set in environment variables.")

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    client = OpenAI(api_key=api_key)

    prompt = f"""
You are an analyst. Find public webpages that contain COMMENTS / REVIEWS / FEEDBACK / DISCUSSIONS about this company.

Company (exact): {company}
Hints (required): {hints}

STRICT RULES:
- Every result MUST be about the same company. Reject anything unrelated.
- Prefer review/comment sources: Google reviews pages, Reddit threads, forums, Trustpilot, complaint boards, news comment pages, community discussions.
- Avoid login-only pages, avoid homepages (use deep links).
- Avoid irrelevant local services (massage/spa/salon/etc.) even if location matches hints.

Return ONLY valid JSON with EXACT structure:
{{
  "results": [
    {{"url":"https://...", "reason":"...", "confidence": 0}}
  ]
}}
Provide 6 to {max_links} results.
"""

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )

    text = (resp.choices[0].message.content or "").strip()

    results: List[Dict] = []
    try:
        data = json.loads(text)
        arr = data.get("results", [])
        if isinstance(arr, list):
            for item in arr:
                url = str(item.get("url", "")).strip()
                reason = str(item.get("reason", "")).strip()
                conf = item.get("confidence", 0)
                try:
                    conf = int(conf)
                except Exception:
                    conf = 0
                if url.startswith("http") and _is_relevant_url(company, hints, url, reason):
                    results.append({"url": url, "reason": reason, "confidence": max(0, min(100, conf))})
    except Exception:
        # fallback: scrape URLs from raw text
        urls = _extract_urls(text)
        for u in urls:
            if _is_relevant_url(company, hints, u, ""):
                results.append({"url": u, "reason": "extracted from model output", "confidence": 50})

    # de-dup keep order
    seen = set()
    final = []
    for r in results:
        if r["url"] not in seen:
            final.append(r)
            seen.add(r["url"])
    return final[:max_links]
