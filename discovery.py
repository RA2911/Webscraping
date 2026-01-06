import json
import os
import re
from typing import List

from openai import OpenAI


def _extract_urls(text: str) -> List[str]:
    # fallback if model returns text with URLs
    urls = re.findall(r"https?://[^\s\]\)\"'>]+", text or "")
    # de-dup preserve order
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
    Uses OpenAI Responses API + web_search tool to return a clean list of URLs
    likely containing comments/reviews/feedback about the company.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set in environment variables.")

    model = os.getenv("OPENAI_MODEL", "gpt-5.2")
    client = OpenAI()

    prompt = f"""
You are an analyst. Find public webpages that contain COMMENTS / REVIEWS / FEEDBACK / DISCUSSIONS about the company.

Company: {company}
Hints (optional): {hints}

Rules:
- Return ONLY a JSON object with this exact structure:
  {{
    "urls": ["https://...", "..."]
  }}
- Provide between 6 and {max_links} URLs.
- Prefer sources that usually contain user commentary: forums, Reddit threads, review pages, complaint boards, community discussions, news comment pages, social posts that are publicly accessible.
- Avoid login-only pages and avoid homepages (prefer deep links with text).
"""

    # Enable web search tool. :contentReference[oaicite:2]{index=2}
    resp = client.responses.create(
        model=model,
        input=prompt,
        tools=[{"type": "web_search"}],
    )

    out_text = getattr(resp, "output_text", None)
    if callable(out_text):
        text = resp.output_text()
    else:
        # fallback: SDK sometimes stores on property
        text = getattr(resp, "output_text", "") or ""

    # Try JSON parse first
    try:
        data = json.loads(text)
        urls = data.get("urls", [])
        if isinstance(urls, list) and urls:
            return [str(u).strip() for u in urls if str(u).strip().startswith("http")]
    except Exception:
        pass

    # fallback: scrape URLs from text
    urls = _extract_urls(text)
    return urls[:max_links]
