import json, requests, time

start = time.time()
print("Starting query against Ollama...")
resp = requests.post(
    "http://localhost:11434/api/chat",
    json={
        "model": "qwen2.5:7b",
        "messages": [{"role": "user", "content": "You are a FinOps expert. Respond with exactly one JSON array containing one test recommendation object: resource, service, action, current_monthly_cost, estimated_savings_monthly, savings_pct, title, finding, why_it_matters, remediation, confidence, priority, category. Make it around 150 words."}],
        "stream": False,
        "options": {"num_predict": 4000, "temperature": 0.2}
    }
)
elapsed = time.time() - start
print(f"Elapsed: {elapsed:.2f}s")
if resp.status_code == 200:
    print(resp.json().get('message', {}).get('content')[:500])
else:
    print(resp.text)
