import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

NOISE_TAGS = ["nav", "footer", "header", "aside", "form", "script", "style"]

def scrape_clean_text(url, timeout=15):
    """
    Fetch a webpage and return cleaned text content
    (basic noise removal).
    """
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Remove obvious noisy tags
    for tag in NOISE_TAGS:
        for el in soup.find_all(tag):
            el.decompose()

    text = soup.get_text(separator="\n", strip=True)
    return text
