import json
import os
import urllib.request

with open(".env") as f:
    for line in f:
        if "=" in line and not line.startswith("#"):
            k, v = line.strip().split("=", 1)
            os.environ[k] = v

key = os.getenv("GEMINI_API_KEY")
print("Key length:", len(key) if key else 0)

for model in ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    payload = {"contents": [{"parts": [{"text": 'Respond with JSON: {"status": "ok"}'}]}]}
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"Model {model} SUCCESS:")
            print(resp.read().decode("utf-8")[:200])
            break
    except Exception as e:
        print(f"Model {model} FAILED:", e)
