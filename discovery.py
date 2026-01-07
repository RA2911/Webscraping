import json
import os
import re
from typing import List

from openai import OpenAI


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


def discover_comment_links(company: str, max_links: int = 12, hints: str = "") -> List[str]:
    """
    Returns a list of URLs that likely contain comments/reviews/feedback about the company.
    NOTE: With openai==1.51.2, we use chat.completions (no client.responses / no web_search tool).
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set in environment variables.")

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    client = OpenAI(api_key=api_key)

    prompt = f"""
You are an analyst. Suggest public webpages that likely contain COMMENTS / REVIEWS / FEEDBACK / DISCUSSIONS about the company.

Company: {company}
Hints (optional): {hints}

Rules:
- Return ONLY a JSON object with this exact structure:
  {{
    "urls": ["https://...", "..."]
  }}
- Provide between 6 and {max_links} URLs.
- Prefer sources that usually contain user commentary: forums, Reddit threads, review pages, complaint boards, community discussions, news comment pages.
- Avoid login-only pages and avoid homepages (prefer deep links with text).
"""

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
    )

    text = (resp.choices[0].message.content or "").strip()

    # Try JSON parse first
    try:
        data = json.loads(text)
        urls = data.get("urls", [])
        if isinstance(urls, list) and urls:
            cleaned = []
            for u in urls:
                u = str(u).strip()
                if u.startswith("http"):
                    cleaned.append(u)
            return cleaned[:max_links]
    except Exception:
        pass

    # fallback: scrape URLs from text
    urls = _extract_urls(text)
    return urls[:max_links]
