from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

DEFAULT_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "gitsage"


def generate(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    url: str = DEFAULT_URL,
    temperature: float = 0.2,
    top_p: float = 0.85,
    timeout: int = 120,
) -> str:
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "top_p": top_p,
        },
    }).encode()

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return data.get("response", "").strip()
    except urllib.error.URLError as exc:
        print(
            f"\n[ERROR] Cannot reach Ollama at {url}\n"
            f"  Make sure Ollama is running:  ollama serve\n"
            f"  Detail: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
