"""LiteLLM kwargs resolution for the model ids this agent accepts.

Kept separate from ``agent_loop`` so tools (research, context compaction, etc.)
can import it without pulling in the whole agent loop / tool router and
creating circular imports.
"""

import os

from agent.core.local_models import (
    LOCAL_MODEL_API_KEY_DEFAULT,
    LOCAL_MODEL_API_KEY_ENV,
    LOCAL_MODEL_BASE_URL_ENV,
    is_reserved_local_model_id,
    local_model_name,
    local_model_provider,
)
from agent.core.model_ids import (
    is_direct_provider_model_id,
)
from agent.core.token_pool import token_pool


class UnsupportedEffortError(ValueError):
    """The requested effort isn't valid for this provider's API surface.

    Raised synchronously before any network call so the probe cascade can
    skip levels the provider can't accept (e.g. ``max`` on HF router).
    """


def _local_api_base(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    if base.endswith("/v1"):
        return base
    return f"{base}/v1"


def _resolve_local_model_params(
    model_name: str,
    reasoning_effort: str | None = None,
    strict: bool = False,
) -> dict:
    if reasoning_effort and strict:
        raise UnsupportedEffortError(
            "Local OpenAI-compatible endpoints don't accept reasoning_effort"
        )

    local_name = local_model_name(model_name)
    if local_name is None:
        raise ValueError(f"Unsupported local model id: {model_name}")

    provider = local_model_provider(model_name)
    assert provider is not None
    raw_base = (
        os.environ.get(provider["base_url_env"])
        or os.environ.get(LOCAL_MODEL_BASE_URL_ENV)
        or provider["base_url_default"]
    )
    api_key = (
        os.environ.get(provider["api_key_env"])
        or os.environ.get(LOCAL_MODEL_API_KEY_ENV)
        or LOCAL_MODEL_API_KEY_DEFAULT
    )
    return {
        "model": f"openai/{local_name}",
        "api_base": _local_api_base(raw_base),
        "api_key": api_key,
    }


def _clean_provider_key(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None


def _direct_provider_api_key(model_name: str) -> str | None:
    if model_name.startswith("gemini/"):
        return _clean_provider_key(
            token_pool.get_token("gemini") or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        )
    if model_name.startswith("mistral/"):
        return _clean_provider_key(
            token_pool.get_token("mistral") or os.environ.get("MISTRAL_API_KEY")
        )
    return None


def _resolve_direct_provider_params(
    model_name: str,
    reasoning_effort: str | None = None,
    strict: bool = False,
) -> dict:
    if reasoning_effort and strict:
        raise UnsupportedEffortError(
            "Direct Gemini/Mistral providers don't accept reasoning_effort"
        )

    return {
        "model": model_name,
        "api_key": _direct_provider_api_key(model_name),
    }


def _resolve_llm_params(
    model_name: str,
    session_hf_token: str | None = None,
    reasoning_effort: str | None = None,
    strict: bool = False,
) -> dict:
    """
    Build LiteLLM kwargs for a given model id.

    • ``ollama/<model>``, ``vllm/<model>``, ``lm_studio/<model>``, and
      ``llamacpp/<model>`` — local OpenAI-compatible endpoints. The id prefix
      selects a configurable localhost base URL, and the model suffix is sent
      to LiteLLM as ``openai/<model>``. These endpoints don't receive
      ``reasoning_effort``.

    • Anything else is passed through to LiteLLM directly.
    """
    normalized_model = model_name

    if is_reserved_local_model_id(normalized_model):
        raise ValueError(f"Unsupported local model id: {normalized_model}")

    if local_model_provider(normalized_model) is not None:
        return _resolve_local_model_params(normalized_model, reasoning_effort, strict)

    if normalized_model in ("openai/auto", "omniroute/auto"):
        route_model = os.environ.get("OMNIROUTE_ROUTE_MODEL", "auto")
        return {
            "model": f"openai/{route_model}",
            "api_base": os.environ.get("OMNIROUTE_BASE_URL", "http://127.0.0.1:20128/v1"),
            "api_key": os.environ.get("OMNIROUTE_API_KEY") or "dummy_omniroute_key",
        }

    if is_direct_provider_model_id(normalized_model):
        return _resolve_direct_provider_params(
            normalized_model,
            reasoning_effort,
            strict,
        )

    # For everything else, pass it through directly to LiteLLM
    # relying on litellm's default env variable resolution (e.g. OPENAI_API_KEY)
    params = {
        "model": normalized_model,
    }
    
    # Optional logic if effort is requested could be added here depending on standard LiteLLM arguments.
    return params
