import requests

key = "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"

r = requests.post(
    "https://api.groq.com/openai/v1/chat/completions",
    headers={"Authorization": f"Bearer {key}"},
    json={
        "model": "llama3-8b-8192",
        "max_tokens": 20,
        "messages": [{"role": "user", "content": "say hello"}]
    },
    timeout=15
)

print("Status:", r.status_code)
print("Response:", r.text[:300])
input("Press Enter to close...")