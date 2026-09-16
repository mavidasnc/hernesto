"""Registry dei modelli OpenRouter e caricamento dei prezzi (migrato da chat.py).

Per aggiungere un modello:
  1. Aggiungi un ModelConfig alla lista MODELS.
  2. json_supported   = True se 'response_format' e' in supported_parameters
     (controlla GET /api/v1/models).
  3. schema_supported = True se 'structured_outputs' e' in supported_parameters.
I prezzi vengono caricati a runtime dall'API.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from .config import OPENROUTER_BASE


@dataclass
class ModelConfig:
    label: str
    id: str
    json_supported: bool    # supporta response_format (json_object)
    schema_supported: bool  # supporta structured_outputs (json_schema)
    price_prompt: float = 0.0      # USD per token (popolato a runtime)
    price_completion: float = 0.0  # USD per token (popolato a runtime)


MODELS: list[ModelConfig] = [
    ModelConfig("Gemma 4 31B (free)", "google/gemma-4-31b-it:free", json_supported=True,  schema_supported=False),
    ModelConfig("Kimi K2.5",          "moonshotai/kimi-k2.5",       json_supported=True,  schema_supported=True),
    ModelConfig("Kimi K2.6",          "moonshotai/kimi-k2.6",       json_supported=True,  schema_supported=True),
    ModelConfig("Gemini 2.5 Flash",   "google/gemini-2.5-flash",    json_supported=True,  schema_supported=True),
    ModelConfig("Qwen 3.7 Plus",      "qwen/qwen3.7-plus",          json_supported=True,  schema_supported=True),
    ModelConfig("Qwen 3.8 27B",       "qwen/qwen3.8-27b",           json_supported=True,  schema_supported=True),
    ModelConfig("DeepSeek V4 Pro",    "deepseek/deepseek-v4-pro",   json_supported=True,  schema_supported=True),
    ModelConfig("MiniMax M3",         "minimax/minimax-m3",         json_supported=True,  schema_supported=False),
]

# Modello selezionato all'avvio (indice 0 = Gemma free)
DEFAULT_MODEL = MODELS[0]


def find_model(model_id: str) -> ModelConfig | None:
    """Cerca un modello nel registry per ID OpenRouter."""
    return next((m for m in MODELS if m.id == model_id), None)


def load_pricing(api_key: str) -> None:
    """Recupera i prezzi live da /api/v1/models e popola il registry."""
    try:
        resp = httpx.get(
            f"{OPENROUTER_BASE}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=5.0,
        )
        resp.raise_for_status()
        api_models = {m["id"]: m for m in resp.json().get("data", [])}

        for model in MODELS:
            api_data = api_models.get(model.id)
            if api_data:
                pricing = api_data.get("pricing", {})
                model.price_prompt = float(pricing.get("prompt", 0) or 0)
                model.price_completion = float(pricing.get("completion", 0) or 0)

    except Exception as exc:
        # Non fatale: lo script funziona lo stesso, ma il costo mostrera' $0.000000
        print(f"[Avviso] Prezzi non caricati dall'API: {exc}")
