import json
import sys
import urllib.request

QUESTION = "Какова была минимальная цена на цинковый лом за все месяцы?"
URL = "http://localhost:8000/ask"

body = {
    "question": QUESTION,
    "top_k": 10,
    "mode": "agent",
    "response_mode": "detailed",
    "conversation_history": [],
    "conversation_id": None,
}

req = urllib.request.Request(
    URL,
    data=json.dumps(body).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)

try:
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    print("STATUS:", data.get("status"))
    print("ANSWER:", data.get("answer"))
    print("CONFIDENCE:", data.get("confidence"))
    print("SQL:", data.get("sql_query"))
    print("RETRY_COUNT:", data.get("retry_count"))
    print("SELF_CORRECTED:", data.get("self_corrected"))
    print("LATENCY_MS:", data.get("latency_ms"))
except urllib.error.HTTPError as e:
    print("HTTP ERROR:", e.code)
    print(e.read().decode("utf-8", errors="replace"))
except Exception as e:
    print("ERROR:", e)
    sys.exit(1)
