"""Central configuration for the EC dispute-resolution multi-agent system.

Model names are declared here in source (required by README section 9.4) and are
mirrored into `metadata.json` at the end of every run.

Hard constraint from the lab spec: every agent must run on a model with
<= 10B parameters. Every entry in MODEL_POOL below satisfies that.
"""

from __future__ import annotations

import os

# --------------------------------------------------------------------------
# LLM providers (all OpenAI-compatible chat-completions endpoints).
#
# `params_b` is the published dense parameter count in billions. The runner
# walks a provider's model list top-down whenever a call fails (429 / 5xx /
# unparseable output), so a rate-limited tier degrades instead of dying.
#
# Model names live here in source, never in .env (README section 9.4).
# --------------------------------------------------------------------------
MAX_PARAMS_B = 10.0

PROVIDERS = {
    # Free tier: 14,400 requests/day but only 6,000 tokens/minute, so throughput
    # is token-bound. `tokens_per_minute` drives the client-side pacer in llm.py.
    # Verified against GET /openai/v1/models: these are the only <=10B chat
    # models Groq still serves (gemma2-9b-it and llama3-8b-8192 were retired).
    "groq": {
        "api_base": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "tokens_per_minute": 6000,
        "models": [
            {"name": "llama-3.1-8b-instant", "params_b": 8.0},
            # Last-resort only: 4k context and tuned for Arabic, so it is a weak
            # fallback — but it keeps a 429 storm from failing the case outright.
            {"name": "allam-2-7b", "params_b": 7.0},
        ],
    },
    # Non-reasoning models are ranked first: this task wants short strict JSON,
    # and <think> preambles are a JSON-extraction hazard, not an accuracy win.
    "openrouter": {
        "api_base": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
        "tokens_per_minute": 0,  # 0 = no client-side pacing
        "models": [
            {"name": "meta-llama/llama-3.1-8b-instruct", "params_b": 8.0},
            {"name": "qwen/qwen-2.5-7b-instruct", "params_b": 7.0},
            {"name": "mistralai/ministral-8b-2512", "params_b": 8.0},
            {"name": "nvidia/nemotron-nano-9b-v2:free", "params_b": 9.0},
            {"name": "google/gemma-3-4b-it", "params_b": 4.0},
        ],
    },
}

# Preference order when several keys are present. Override with LLM_PROVIDER.
PROVIDER_PREFERENCE = ["groq", "openrouter"]


def resolve_provider() -> str:
    """Pick the provider whose API key is actually available."""
    forced = os.getenv("LLM_PROVIDER", "").strip().lower()
    if forced:
        if forced not in PROVIDERS:
            raise ValueError(f"unknown LLM_PROVIDER '{forced}'; expected one of {list(PROVIDERS)}")
        return forced
    for name in PROVIDER_PREFERENCE:
        if os.getenv(PROVIDERS[name]["key_env"]):
            return name
    return PROVIDER_PREFERENCE[0]


def provider_config(name: str) -> dict:
    entry = PROVIDERS[name]
    return {
        "provider": name,
        # LLM_API_BASE still wins, so a local vLLM/Ollama server can be dropped in.
        "api_base": os.getenv("LLM_API_BASE") or entry["api_base"],
        "key_env": entry["key_env"],
        "models": entry["models"],
        "primary_model": entry["models"][0]["name"],
        "tokens_per_minute": entry.get("tokens_per_minute", 0),
    }


for _name, _entry in PROVIDERS.items():
    assert all(m["params_b"] <= MAX_PARAMS_B for m in _entry["models"]), (
        f"Lab rule violated: every model for provider '{_name}' must be <= 10B parameters."
    )

# --------------------------------------------------------------------------
# Sampling + transport
# --------------------------------------------------------------------------
TEMPERATURE = 0.0          # deterministic reasoning; this is a compliance task
MAX_TOKENS = 500           # replies are small JSON objects; caps TPM burn
REQUEST_TIMEOUT_S = 90
MAX_RETRIES_PER_MODEL = 3
CASE_WORKERS = 3           # cases processed concurrently
AGENT_WORKERS = 3          # domain agents fan out inside one case

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data")
INPUT_DIR = os.path.join(REPO_ROOT, "input")
OUTPUT_DIR = os.path.join(REPO_ROOT, "output")
LOG_DIR = os.path.join(REPO_ROOT, "logging")

POLICY_VERSION = "EC_POLICY_V1"
CURRENCY = "BRL"

# Output caps from README section 6.
MAX_ENTITY_IDS = 5
MAX_EVIDENCE = 10
MAX_ROOT_CAUSES = 3
MAX_RESPONSIBLE_PARTIES = 3
MAX_ACTIONS = 5

# Payment reconciliation tolerance from the policy table.
PAYMENT_TOLERANCE_BRL = 0.10
