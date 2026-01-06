import re
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
    "consent", "privacy", "gdpr"
]

def is_valid_url(u: str) -> bool:
    try:
        p = urlparse(u.strip())
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False

def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def clean_with_bs4(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")

    # remove obvious noise tags
    for tag in NOISE_TAGS:
        for el in soup.find_all(tag):
            el.decompose()

    # remove blocks by common noise class/id hints
    for el in soup.find_all(True):
        class_list = el.get("class", [])
        if not isinstance(class_list, list):
            class_list = [str(class_list)]
        attrs = (" ".join(class_list) + " " + str(el.get("id") or "")).lower()
        if any(h in attrs for h in NOISE_HINTS):
            el.decompose()

    text = soup.get_text(separator="\n", strip=True)
    return normalize_text(text)

def scrape_clean_text(url: str, timeout: int = 20) -> str:
    """
    Returns clean main text for a single URL.
    Strategy:
      1) trafilatura extract (best for main content)
      2) readability-lxml -> bs4 clean (good fallback)
      3) full bs4 clean fallback
    """
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    html = r.text

    # 1) trafilatura main extraction
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
            return extracted

    # 2) readability main section, then clean
    doc = Document(html)
    main_html = doc.summary(html_partial=True)
    main_text = clean_with_bs4(main_html)
    if len(main_text) >= 300:
        return main_text

    # 3) fallback: clean full page (still removes many menus/footers)
    fallback = clean_with_bs4(html)
    if len(fallback) >= 300:
        return fallback

    return "No readable main content extracted (page may be JS-rendered, blocked, or too short)."

