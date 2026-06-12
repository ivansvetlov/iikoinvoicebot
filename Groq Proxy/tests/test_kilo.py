#!/usr/bin/env python3
import requests
import json

url = "http://localhost:8080/v1/chat/completions"
headers = {"Content-Type": "application/json"}
data = {
    "messages": [{"role": "user", "content": "say hi"}],
    "model": "grok",
    "stream": False
}

print("Отправка запроса в Kilo Code формате...")
response = requests.post(url, headers=headers, json=data)
print(f"Status: {response.status_code}")
print(f"Response: {response.text}")
