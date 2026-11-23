import os
import subprocess
import sys
import time
import uuid
from collections import defaultdict
import gradio as gr
import httpx
from bs4 import BeautifulSoup
# 1. Force google-scraper backend onto port 8000 so Gradio gets Render's $PORT
backend_env = os.environ.copy()
backend_env["PORT"] = "8000"
subprocess.Popen([sys.executable, "run.py"], cwd="google-scraper", env=backend_env)
time.sleep(2)


# 2. API Key + IP Rate Limiter (30 req/min per IP)
VALID_KEYS = {"sk-free-master-key"}
REQUEST_LOG = defaultdict(list)
RATE_LIMIT_PER_MIN = 30


def check_ip_and_key(request: gr.Request, api_key: str = ""):
    client_ip = request.client.host if request and request.client else "unknown"
    now = time.time()
    REQUEST_LOG[client_ip] = [t for t in REQUEST_LOG[client_ip] if now - t < 60]

    if len(REQUEST_LOG[client_ip]) >= RATE_LIMIT_PER_MIN:
        return False, f"Rate limit exceeded for IP {client_ip} (max {RATE_LIMIT_PER_MIN}/min)."

    REQUEST_LOG[client_ip].append(now)

    if not api_key or api_key.strip() not in VALID_KEYS:
        return False, "Invalid or missing API key."

    return True, client_ip


def generate_api_key():
    new_key = "sk-free-" + uuid.uuid4().hex
    VALID_KEYS.add(new_key)
    return new_key


def fetch_live_cricket(filter_query: str = ""):
    try:
        res = httpx.get(
            "https://site.api.espn.com/apis/site/v2/sports/cricket/scorepanel",
            timeout=20.0,
        )
        data = res.json()
        matches = []
        q = (filter_query or "").strip().lower()

        for item in data.get("scores", []):
            league = item.get("leagues", [{}])[0].get("name", "")
            for event in item.get("events", []):
                name = event.get("name", "")
                status = event.get("status", {}).get("type", {}).get("detail", "")
                comp = event.get("competitions", [{}])[0]
                teams = [
                    {
                        "team": c.get("team", {}).get("displayName", ""),
                        "score": c.get("score", "Yet to bat"),
                    }
                    for c in comp.get("competitors", [])
                ]
                if not q or q in name.lower() or q in league.lower():
                    matches.append({"series": league, "match": name, "status": status, "scores": teams})

        return {"source": "ESPN Live Cricket Scorepanel", "count": len(matches), "matches": matches}
    except Exception as e:
        return {"error": str(e)}


def fetch_lightweight_ai_overview(query: str):
    """Fast, CAPTCHA-free AI Overview + web results using < 50 MB RAM."""
    results = []
    overview_parts = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0.0.0 Safari/537.36"}

    try:
        ddg = httpx.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers=headers,
            timeout=15.0,
        )
        soup = BeautifulSoup(ddg.text, "lxml")
        for item in soup.select(".result")[:6]:
            title_el = item.select_one(".result__a")
            snip_el = item.select_one(".result__snippet")
            if title_el:
                title = title_el.get_text(strip=True)
                link = title_el.get("href", "")
                snippet = snip_el.get_text(" ", strip=True) if snip_el else ""
                results.append({"title": title, "url": link, "snippet": snippet})
                if snippet and len(overview_parts) < 3:
                    overview_parts.append(snippet)
    except Exception:
        pass

    try:
        wiki = httpx.get(
            "https://en.wikipedia.org/w/api.php",
            params={"action": "opensearch", "search": query, "limit": 1, "format": "json"},
            headers=headers,
            timeout=10.0,
        ).json()
        if len(wiki) >= 4 and wiki[2] and wiki[2][0]:
            overview_parts.insert(0, wiki[2][0])
    except Exception:
        pass

    ai_summary = " ".join(overview_parts).strip() or "No overview summary available for this query."
    return {
        "query": query,
        "ai_overview": ai_summary,
        "organic_results": results,
        "engine": "lightweight-cloud-overview",
    }


def unified_search(query: str, mode: str, api_key: str, request: gr.Request):
    allowed, info = check_ip_and_key(request, api_key)
    if not allowed:
        return {"error": info, "ip_protected": True}

    if mode == "Live Cricket Scores (Real-Time)":
        return fetch_live_cricket(query)

    if not query or not query.strip():
        return {"error": "Please enter a search query."}

    if mode == "AI Overview + Full Google Search":
        return fetch_lightweight_ai_overview(query)

    endpoint_map = {
        "Google News (Live Headlines)": "/news/search",
        "Google Finance (Stock/Crypto Quote)": "/finance/quote",
        "Google Trends (Trending Now)": "/trends/trending",
        "Google Patents": "/patents/search",
        "Google Autocomplete": "/autocomplete",
    }
    endpoint = endpoint_map.get(mode, "/news/search")

    try:
        res = httpx.get(
            f"http://127.0.0.1:8000{endpoint}",
            params={"query": query},
            timeout=30.0,
        )
        return res.json()
    except Exception as e:
        return {"error": str(e)}


with gr.Blocks(title="Live Google Search, AI Overview & Cricket API") as demo:
    gr.Markdown("# Live Google Search, AI Overview & Cricket API")
    with gr.Row():
        mode_in = gr.Dropdown(
            choices=[
                "AI Overview + Full Google Search",
                "Live Cricket Scores (Real-Time)",
                "Google News (Live Headlines)",
                "Google Finance (Stock/Crypto Quote)",
                "Google Trends (Trending Now)",
                "Google Patents",
                "Google Autocomplete",
            ],
            value="AI Overview + Full Google Search",
            label="Mode",
        )
        query_in = gr.Textbox(label="Query", placeholder="e.g. India vs New Zealand live score")
        key_in = gr.Textbox(label="API Key", value="sk-free-master-key")
        btn = gr.Button("Search", variant="primary")

    with gr.Row():
        gen_btn = gr.Button("Generate New API Key")
        gen_out = gr.Textbox(label="Generated Key", interactive=False)
        gen_btn.click(fn=generate_api_key, outputs=gen_out)

    out = gr.JSON(label="Response")
    btn.click(fn=unified_search, inputs=[query_in, mode_in, key_in], outputs=out)
    query_in.submit(fn=unified_search, inputs=[query_in, mode_in, key_in], outputs=out)

port = int(os.environ.get("PORT", 10000))
demo.launch(server_name="0.0.0.0", server_port=port)
