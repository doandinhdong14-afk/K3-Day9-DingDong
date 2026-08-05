"""Minimal OpenAI-compatible chat client (Python stdlib only).

Deliberately dependency-free: `urllib.request` is enough for a chat-completions
POST, which keeps the lab reproducible on a bare Python 3.9+ install.

Two behaviours matter for this lab:

1. **Model fallback.** Free tiers rate-limit hard. On 429/5xx/timeouts the client
   walks `config.MODEL_POOL` top-down. Every model in that pool is <= 10B params,
   so a fallback can never violate the lab constraint.
2. **JSON discipline.** 8B models wrap JSON in prose or fences. `chat_json`
   strips fences, extracts the outermost object, and on failure retries once with
   a stricter reminder before giving up and letting the caller degrade.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

from . import config


class LLMError(RuntimeError):
    pass


class TokenPacer:
    """Client-side sliding-window limiter for a tokens-per-minute quota.

    Groq's free tier allows 14,400 requests/day but only 6,000 tokens/minute, so
    throughput here is token-bound, not request-bound. Pacing to the budget turns
    what would be a continuous 429 retry storm into smooth progress.
    """

    def __init__(self, tokens_per_minute: int) -> None:
        self.tpm = tokens_per_minute
        self._window: deque = deque()  # (timestamp, tokens)
        self._lock = threading.Lock()
        self.waited_seconds = 0.0

    def acquire(self, estimated_tokens: int) -> None:
        if self.tpm <= 0:
            return
        estimated_tokens = min(estimated_tokens, self.tpm)
        while True:
            with self._lock:
                now = time.time()
                while self._window and now - self._window[0][0] >= 60.0:
                    self._window.popleft()
                used = sum(tokens for _, tokens in self._window)
                if used + estimated_tokens <= self.tpm:
                    self._window.append((now, estimated_tokens))
                    return
                sleep_for = 60.0 - (now - self._window[0][0]) + 0.05
            time.sleep(min(max(sleep_for, 0.1), 10.0))
            with self._lock:
                self.waited_seconds += min(max(sleep_for, 0.1), 10.0)


def estimate_tokens(messages: List[Dict[str, str]]) -> int:
    """Rough char/4 heuristic plus headroom for the reply."""
    chars = sum(len(m.get("content", "")) for m in messages)
    return chars // 4 + 220


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def load_dotenv(path: Optional[str] = None) -> None:
    """Tiny .env loader (no python-dotenv dependency). Never overwrites real env."""
    path = path or os.path.join(config.REPO_ROOT, ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and value and key not in os.environ:
                os.environ[key] = value


def _extract_json(text: str) -> Optional[dict]:
    candidate = text.strip()
    fenced = _FENCE_RE.search(candidate)
    if fenced:
        candidate = fenced.group(1).strip()
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(candidate[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


class LLMClient:
    """Thread-safe chat client with usage accounting."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        load_dotenv()
        self.provider = config.resolve_provider()
        settings = config.provider_config(self.provider)
        self.models = settings["models"]
        self.primary_model = settings["primary_model"]
        self.base_url = settings["api_base"].rstrip("/")
        self.api_key = api_key or os.getenv(settings["key_env"], "")
        if not self.api_key:
            raise LLMError(
                f"{settings['key_env']} is not set. Copy .env.example to .env and paste your key."
            )
        self.pacer = TokenPacer(settings["tokens_per_minute"])
        self._lock = threading.Lock()
        self.stats = {
            "calls": 0,
            "failed_calls": 0,
            "rate_limited": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "json_repairs": 0,
            "model_calls": {},
        }

    # ------------------------------------------------------------- transport
    def _post(self, model: str, messages: List[Dict[str, str]]) -> Tuple[str, dict]:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": config.TEMPERATURE,
            "max_tokens": config.MAX_TOKENS,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            # Groq's edge rejects the default "Python-urllib/x.y" agent with 403.
            "User-Agent": "K3-Day9-DingDong/1.0 (+multi-agent dispute resolution lab)",
        }
        if self.provider == "openrouter":  # optional attribution headers
            headers["HTTP-Referer"] = "https://github.com/doandinhdong14-afk/K3-Day9-DingDong"
            headers["X-Title"] = "K3 Day9 EC Dispute Multi-Agent"
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        self.pacer.acquire(estimate_tokens(messages))
        with urllib.request.urlopen(request, timeout=config.REQUEST_TIMEOUT_S) as response:
            body = json.loads(response.read().decode("utf-8"))
        if "choices" not in body or not body["choices"]:
            raise LLMError(f"malformed response from {model}: {str(body)[:200]}")
        return body["choices"][0]["message"].get("content") or "", body.get("usage", {})

    def chat(self, messages: List[Dict[str, str]]) -> Tuple[str, str]:
        """Returns (content, model_actually_used). Walks the <=10B model pool."""
        last_error: Optional[Exception] = None
        for entry in self.models:
            model = entry["name"]
            for attempt in range(config.MAX_RETRIES_PER_MODEL):
                try:
                    content, usage = self._post(model, messages)
                    with self._lock:
                        self.stats["calls"] += 1
                        self.stats["prompt_tokens"] += usage.get("prompt_tokens", 0)
                        self.stats["completion_tokens"] += usage.get("completion_tokens", 0)
                        self.stats["model_calls"][model] = self.stats["model_calls"].get(model, 0) + 1
                    return content, model
                except urllib.error.HTTPError as exc:
                    last_error = exc
                    if exc.code in (429, 500, 502, 503, 504):
                        if exc.code == 429:
                            with self._lock:
                                self.stats["rate_limited"] += 1
                        # Honour the server's own backoff hint when it sends one.
                        retry_after = exc.headers.get("retry-after") if exc.headers else None
                        try:
                            delay = float(retry_after) if retry_after else 1.5 * (attempt + 1)
                        except ValueError:
                            delay = 1.5 * (attempt + 1)
                        time.sleep(min(delay, 30.0))
                        continue
                    break  # 4xx other than rate limit: next model won't help either
                except Exception as exc:  # timeouts, connection resets
                    last_error = exc
                    time.sleep(1.0 * (attempt + 1))
        with self._lock:
            self.stats["failed_calls"] += 1
        raise LLMError(
            f"all <=10B models on provider '{self.provider}' failed; last error: {last_error}"
        )

    # ------------------------------------------------------------ structured
    def chat_json(self, system: str, user: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Ask for one JSON object. Returns (parsed, meta)."""
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        raw, model = self.chat(messages)
        parsed = _extract_json(raw)
        repaired = False
        if parsed is None:
            repaired = True
            with self._lock:
                self.stats["json_repairs"] += 1
            messages = messages + [
                {"role": "assistant", "content": raw[:800]},
                {
                    "role": "user",
                    "content": "That was not valid JSON. Reply again with ONLY the JSON object, "
                    "no prose, no markdown fences, no explanation.",
                },
            ]
            raw, model = self.chat(messages)
            parsed = _extract_json(raw)
        if parsed is None:
            raise LLMError(f"model {model} did not return parseable JSON: {raw[:200]}")
        return parsed, {"model": model, "json_repaired": repaired, "raw_chars": len(raw)}
