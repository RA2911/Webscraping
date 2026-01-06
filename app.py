import io
from datetime import datetime

from flask import Flask, render_template, request, send_file

from scraper import is_valid_url, scrape_clean_text

app = Flask(__name__)


def build_combined_txt(urls: list[str]) -> str:
    out = []
    out.append(f"Scraped on (UTC): {datetime.utcnow().isoformat()}Z")
    out.append("")

    for url in urls:
        out.append("=" * 80)
        out.append(f"URL: {url}")
        out.append("=" * 80)
        try:
            text = scrape_clean_text(url)
            out.append(text)
        except Exception as e:
            out.append(f"ERROR: {e}")
        out.append("")

    return "\n".join(out).strip() + "\n"


@app.get("/")
def home():
    return render_template("index.html", results=None, urls_text="")


@app.post("/scrape")
def scrape():
    urls_text = request.form.get("urls", "")
    raw_urls = [u.strip() for u in urls_text.splitlines() if u.strip()]
    urls = [u for u in raw_urls if is_valid_url(u)]

    results = []
    for url in urls:
        try:
            text = scrape_clean_text(url)
            preview = text[:2000] + ("\n...\n(TRUNCATED PREVIEW)" if len(text) > 2000 else "")
            results.append({"url": url, "ok": True, "text": preview})
        except Exception as e:
            results.append({"url": url, "ok": False, "text": str(e)})

    return render_template("index.html", results=results, urls_text=urls_text)


@app.post("/download")
def download():
    urls_text = request.form.get("urls", "")
    raw_urls = [u.strip() for u in urls_text.splitlines() if u.strip()]
    urls = [u for u in raw_urls if is_valid_url(u)]

    combined = build_combined_txt(urls)
    mem = io.BytesIO(combined.encode("utf-8"))
    mem.seek(0)

    return send_file(
        mem,
        as_attachment=True,
        download_name="scraped_content.txt",
        mimetype="text/plain",
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

