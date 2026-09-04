import json
import os
import urllib.error
import urllib.request

with open(".env") as f:
    for line in f:
        if "=" in line and not line.startswith("#"):
            k, v = line.strip().split("=", 1)
            os.environ[k] = v

key = os.getenv("GEMINI_API_KEY")
print("Key length:", len(key))

url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}"
payload = {
    "contents": [
        {
            "parts": [
                {"text": "Classify this error: payment failed"}
            ]
        }
    ]
}

req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")

try:
    with urllib.request.urlopen(req) as resp:
        print("Success:", resp.read().decode())
except urllib.error.HTTPError as e:
    print("HTTP Error Code:", e.code)
    print("Error Body:", e.read().decode("utf-8"))
except Exception as e:
    print("Exception:", e)
