import io
import os
import threading
import time
from typing import Dict, Any, List

from flask import Flask, jsonify, render_template, request, send_file

from discovery import discover_comment_links
from scraper import scrape_many, build_combined_txt, ScrapeItem
from kpi_engine import build_dashboard_payload
from openai import OpenAI

app = Flask(__name__)

# HARD DISABLE PROXIES (Render / httpx fix)
for k in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]:
    os.environ.pop(k, None)

STATE: Dict[str, Any] = {
    "status": "idle",   # idle|running|done|error
    "step": "",
    "progress": 0,      # 0..100
    "company": "",
    "urls": [],
    "items": [],        # list of {url, ok, text_preview, error?}
    "combined_txt": "",
    "dashboard": None,
    "predictive": None,
    "error": None,
}

LOCK = threading.Lock()


def _slow_progress(target: int, seconds: float = 1.2):
    # Smooth slow progress: incremental steps
    with LOCK:
        cur = int(STATE.get("progress", 0))
    if target <= cur:
        return
    steps = max(1, target - cur)
    sleep = max(0.02, seconds / steps)
    for p in range(cur + 1, target + 1):
        with LOCK:
            STATE["progress"] = p
        time.sleep(sleep)


def _set_step(step: str, target_progress: int):
    with LOCK:
        STATE["step"] = step
    _slow_progress(target_progress, seconds=1.6)


def _run_pipeline(company: str, max_links: int = 12, hints: str = ""):
    try:
        with LOCK:
            STATE.update({
                "status": "running",
                "step": "Starting…",
                "progress": 0,
                "company": company,
                "urls": [],
                "items": [],
                "combined_txt": "",
                "dashboard": None,
                "predictive": None,
                "error": None,
            })

        _set_step("Discovering public comment links…", 18)
        urls = discover_comment_links(company=company, max_links=max_links, hints=hints)
        urls = [u for u in urls if u.startswith("http")]
        urls = urls[:max_links]

        with LOCK:
            STATE["urls"] = urls

        _set_step("Fetching pages…", 40)
        items: List[ScrapeItem] = scrape_many(urls, max_pages=max_links)

        # preview cards
        cards = []
        ok_texts = []
        for it in items:
            if it.ok:
                ok_texts.append(it.text)
                preview = it.text[:1200] + ("\n...\n(TRUNCATED)" if len(it.text) > 1200 else "")
                cards.append({"url": it.url, "ok": True, "preview": preview})
            else:
                cards.append({"url": it.url, "ok": False, "preview": it.text})

        with LOCK:
            STATE["items"] = cards

        _set_step("Cleaning & merging sources…", 62)
        combined = build_combined_txt(company=company, items=items)
        with LOCK:
            STATE["combined_txt"] = combined

        _set_step("Computing KPIs…", 82)
        dashboard = build_dashboard_payload(company=company, corpus_texts=ok_texts)
        with LOCK:
            STATE["dashboard"] = dashboard

        _set_step("Dashboard ready", 100)
        with LOCK:
            STATE["status"] = "done"
            STATE["step"] = "Done"

    except Exception as e:
        with LOCK:
            STATE["status"] = "error"
            STATE["error"] = str(e)
            STATE["step"] = "Failed"
            STATE["progress"] = 100


@app.get("/")
def home():
    return render_template("index.html")


@app.post("/api/run")
def api_run():
    data = request.get_json(force=True)
    company = (data.get("company") or "").strip()
    hints = (data.get("hints") or "").strip()
    max_links = int(data.get("max_links") or 12)

    if not company:
        return jsonify({"ok": False, "error": "Company name is required."}), 400

    # Make sure key exists for discovery + predictive calls
    if not os.getenv("OPENAI_API_KEY"):
        return jsonify({"ok": False, "error": "OPENAI_API_KEY is not set in Render env."}), 400

    t = threading.Thread(target=_run_pipeline, args=(company, max_links, hints), daemon=True)
    t.start()
    return jsonify({"ok": True})


@app.get("/api/status")
def api_status():
    with LOCK:
        return jsonify(STATE)


@app.post("/api/predictive")
def api_predictive():
    """
    Predictive actions based on computed KPIs and evidence.
    Sorted: most urgent -> least urgent. max 5 actions.
    """
    with LOCK:
        dash = STATE.get("dashboard")
        company = STATE.get("company")
        if not dash:
            return jsonify({"ok": False, "error": "Run intelligence first."}), 400

    client = OpenAI()
    model = os.getenv("OPENAI_MODEL", "gpt-5.2")

    overall_rate = dash.get("overall_sentiment_rate")
    masters = dash.get("masters", {})
    evidence = dash.get("evidence", {})

    prompt = f"""
You are a crisis-and-growth analyst.

Company: {company}
Overall Sentiment Rate (0-100): {overall_rate}

KPIs (summary):
{masters}

Evidence (most negative excerpts):
{evidence.get("most_negative", [])}

Task:
- Provide MAX 5 actions.
- Sort strictly from MOST critical & urgent to LEAST urgent.
- For each action, estimate:
  - Expected uplift in Overall Sentiment Rate (e.g., +3.5 points)
  - Time horizon (e.g., 2 weeks, 1 month, 3 months)
  - Which KPIs it improves
- Output ONLY JSON:
{{
  "actions": [
    {{
      "rank": 1,
      "title": "...",
      "urgency": "Critical|High|Medium|Low",
      "why": "...",
      "kpis_impacted": ["..."],
      "expected_uplift_points": 0.0,
      "time_horizon": "..."
    }}
  ]
}}
"""

    resp = client.responses.create(model=model, input=prompt)
    text = resp.output_text()

    import json
    try:
        data = json.loads(text)
    except Exception:
        return jsonify({"ok": False, "error": "Predictive response was not valid JSON."}), 500

    actions = data.get("actions", [])
    with LOCK:
        STATE["predictive"] = actions

    return jsonify({"ok": True, "actions": actions})


@app.get("/download/txt")
def download_txt():
    with LOCK:
        txt = STATE.get("combined_txt", "")
        company = (STATE.get("company") or "company").strip().replace(" ", "_")

    if not txt:
        return jsonify({"ok": False, "error": "No TXT available. Run intelligence first."}), 400

    mem = io.BytesIO(txt.encode("utf-8"))
    mem.seek(0)
    return send_file(mem, as_attachment=True, download_name=f"{company}_scraped_content.txt", mimetype="text/plain")
