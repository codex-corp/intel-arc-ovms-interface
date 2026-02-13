# Connecting AI Tools to Local OVMS

Your Intel Arc A750 inference server is OpenAI-compatible, but with one critical difference: **it uses the `/v3` endpoint instead of `/v1`.**

Most tools will work **directly** (no proxy needed) if you configure the **Base URL** correctly.

## ⚙️ General Configuration

- **API Type:** OpenAI / OpenAI Compatible
- **Base URL:** `http://localhost:8000/v3`
  - *Note: If a tool appends `/v1` automatically, set URL to `http://localhost:8000/v3` and hope it doesn't force `/v1`.*
- **API Key:** `sk-dummy` (or any string)
- **Model Name:** `qwen2.5-coder-7b` (Must match exactly)

---

## 🔌 VS Code Extensions

### 1. Continue (continue.dev)
Edit `~/.continue/config.json`:
```json
{
  "models": [
    {
      "title": "Local Qwen (Arc GPU)",
      "provider": "openai",
      "model": "qwen2.5-coder-7b",
      "apiBase": "http://localhost:8000/v3",
      "apiKey": "sk-dummy"
    }
  ]
}
```

### 2. Cline / Roo Code
- **Provider:** OpenAI Compatible
- **Base URL:** `http://localhost:8000/v3`
- **Model ID:** `qwen2.5-coder-7b`

---

## 🐍 Open Interpreter (Python)

Run from terminal:

```bash
interpreter --api_base "http://localhost:8000/v3" --model "qwen2.5-coder-7b" --api_key "sk-dummy"
```

---

## 💻 Python Script Example

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v3",
    api_key="sk-dummy",
)

response = client.chat.completions.create(
    model="qwen2.5-coder-7b",
    messages=[{"role": "user", "content": "Write a binary search in Python"}],
    stream=True,
)

for chunk in response:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

## ❓ Troubleshooting

**"Model not found" or 404 Error:**
- Did you use `/v1`? Change it to `/v3`.
- Did you use the wrong model name? It must be exactly `qwen2.5-coder-7b`.

**"Connection refused":**
- Is the server running? Check `powershell` window for "Status change to: AVAILABLE".
- Start it with `.\start_server.ps1`.
