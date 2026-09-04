import json
import os
import urllib.request

with open(".env") as f:
    for line in f:
        if "=" in line and not line.startswith("#"):
            k, v = line.strip().split("=", 1)
            os.environ[k] = v

key = os.getenv("GEMINI_API_KEY")

for model in ["gemini-2.5-flash", "gemini-3.8-flash", "gemini-3.5-flash", "gemini-flash-latest"]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": "Respond with JSON containing category: card_expired, confidence: 0.9, reasoning: test"}
                ]
            }
        ]
    }

    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")

    try:
        with urllib.request.urlopen(req) as resp:
            print(f"Model {model} SUCCESS:")
            data = json.loads(resp.read().decode("utf-8"))
            print(data["candidates"][0]["content"]["parts"][0]["text"])
            break
    except Exception as e:
        print(f"Model {model} FAILED:", e)
