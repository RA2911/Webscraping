import re
from dataclasses import dataclass
from typing import List, Tuple
from urllib.parse import urlparse

import requests
import trafilatura
from bs4 import BeautifulSoup
from readability import Document


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

NOISE_TAGS = ["nav", "footer", "header", "aside", "form", "noscript", "script", "style"]
NOISE_HINTS = [
    "menu", "navbar", "footer", "cookie", "banner", "subscribe", "sidebar", "promo",
    "advert", "ad-", "ads", "modal", "popup", "newsletter", "breadcrumb", "social",
    "consent", "privacy", "gdpr", "terms", "login", "signup"
]


def is_valid_url(u: str) -> bool:
    try:
        p = urlparse(u.strip())
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False


def normalize_text(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_with_bs4(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")

    for tag in NOISE_TAGS:
        for el in soup.find_all(tag):
            el.decompose()

    # remove blocks by id/class hints
    for el in soup.find_all(True):
        class_list = el.get("class", [])
        if not isinstance(class_list, list):
            class_list = [str(class_list)]
        attrs = (" ".join(class_list) + " " + str(el.get("id") or "")).lower()
        if any(h in attrs for h in NOISE_HINTS):
            el.decompose()

    return normalize_text(soup.get_text(separator="\n", strip=True))


def scrape_clean_text(url: str, timeout: int = 20) -> Tuple[bool, str]:
    """
    Returns (ok, text_or_error).
    Handles typical blocks (403) by reporting clearly.
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 403:
            return False, "403 Forbidden (blocked by site anti-bot rules)"
        r.raise_for_status()
        html = r.text

        # 1) trafilatura main content
        extracted = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            include_links=False,
            favor_precision=True
        )
        if extracted:
            extracted = normalize_text(extracted)
            if len(extracted) >= 300:
                return True, extracted

        # 2) readability main section + cleanup
        doc = Document(html)
        main_html = doc.summary(html_partial=True)
        main_text = clean_with_bs4(main_html)
        if len(main_text) >= 300:
            return True, main_text

        # 3) fallback full clean
        fallback = clean_with_bs4(html)
        if len(fallback) >= 300:
            return True, fallback

        return False, "Content extracted is too short (JS-rendered page, empty, or blocked)."

    except requests.RequestException as e:
        return False, f"Request failed: {e}"
    except Exception as e:
        return False, f"Unexpected scrape error: {e}"


@dataclass
class ScrapeItem:
    url: str
    ok: bool
    text: str


def scrape_many(urls: List[str], max_pages: int = 12) -> List[ScrapeItem]:
    clean = []
    count = 0
    for u in urls:
        if count >= max_pages:
            break
        if not is_valid_url(u):
            continue
        ok, txt = scrape_clean_text(u)
        clean.append(ScrapeItem(url=u, ok=ok, text=txt))
        count += 1
    return clean


def build_combined_txt(company: str, items: List[ScrapeItem]) -> str:
    out = []
    out.append(f"Company: {company}")
    out.append("")
    for it in items:
        out.append("=" * 80)
        out.append(f"URL: {it.url}")
        out.append(f"STATUS: {'OK' if it.ok else 'ERROR/BLOCKED'}")
        out.append("=" * 80)
        out.append(it.text)
        out.append("")
    return "\n".join(out).strip() + "\n"
