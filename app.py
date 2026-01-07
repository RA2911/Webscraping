import os
import json
from flask import Flask, request, jsonify

from discovery import discover_comment_links
from scraper import scrape_many, build_combined_txt, ScrapeItem
from kpi_engine import build_dashboard_payload

from openai import OpenAI

app = Flask(__name__)


@app.post("/api/discover")
def api_discover():
    data = request.get_json(force=True)
    company = (data.get("company") or "").strip()
    hints = (data.get("hints") or "").strip()
    if not company:
        return jsonify({"error": "company is required"}), 400

    results = discover_comment_links(company=company, max_links=12, hints=hints)
    return jsonify({"company": company, "hints": hints, "results": results})


@app.post("/api/analyze")
def api_analyze():
    data = request.get_json(force=True)
    company = (data.get("company") or "").strip()
    hints = (data.get("hints") or "").strip()
    selected_urls = data.get("urls")  # optional list

    if not company:
        return jsonify({"error": "company is required"}), 400

    # If user didn't send selected URLs, use discovery results
    if not selected_urls:
        discovered = discover_comment_links(company=company, max_links=12, hints=hints)
        urls = [x["url"] for x in discovered]
    else:
        urls = [str(u).strip() for u in selected_urls if str(u).strip().startswith("http")]

    corpus = []
    blocked_meta = []
    used = []

    for url in urls:
        text, meta = fetch_and_extract(url)
        if meta.get("blocked") or not text:
            blocked_meta.append(meta)
            continue
        corpus.append(text)
        used.append(url)

    payload = build_dashboard_payload(company=company, corpus_texts=corpus, blocked_meta=blocked_meta)
    payload["used_urls"] = used
    payload["blocked"] = blocked_meta

    return jsonify(payload)


@app.post("/api/predictive")
def api_predictive():
    """
    Input: { company, overall_sentiment_rate, evidence?, hints? }
    Output: { actions: [ {title, urgency, impact_pct, timeframe, rationale} ] }
    """
    data = request.get_json(force=True)
    company = (data.get("company") or "").strip()
    rate = data.get("overall_sentiment_rate")
    hints = (data.get("hints") or "").strip()

    if not company:
        return jsonify({"error": "company is required"}), 400

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return jsonify({"error": "OPENAI_API_KEY missing"}), 500

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    client = OpenAI(api_key=api_key)

    prompt = f"""
You are an expert reputation and customer-experience analyst.

Company: {company}
Hints: {hints}
Current Overall Sentiment Rate (0-100): {rate}

Task:
Return maximum 5 actions to improve the Overall Sentiment Rate.
Actions MUST be sorted from MOST urgent/critical to LEAST urgent.

Return ONLY valid JSON:
{{
  "actions": [
    {{
      "title": "...",
      "urgency": "Critical|High|Medium|Low",
      "impact_pct": 0,
      "timeframe": "2-4 weeks|1-3 months|3-6 months",
      "rationale": "short explanation"
    }}
  ]
}}
Rules:
- Impact must be realistic, numeric (0-25).
- Do not add extra keys.
"""

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )

    text = (resp.choices[0].message.content or "").strip()

    try:
        out = json.loads(text)
        actions = out.get("actions", [])
        if not isinstance(actions, list):
            raise ValueError("actions not a list")
        return jsonify({"actions": actions[:5]})
    except Exception:
        return jsonify({"actions": [], "error": "Predictive parsing failed", "raw": text}), 200
