"""Canonical model ids for Router inference."""

GEMINI_MODEL_ID = "gemini/gemini-2.5-pro"
MISTRAL_MODEL_ID = "openai/auto"

# Keep these as verbatim HF Router ids; version punctuation differs by model.
CLAUDE_OPUS_48_MODEL_ID = "anthropic/claude-opus-4.8:fal-ai"
GPT_55_MODEL_ID = "openai/gpt-5.5:fal-ai"
KIMI_K27_CODE_MODEL_ID = "moonshotai/Kimi-K2.7-Code:novita"
MINIMAX_M3_MODEL_ID = "MiniMaxAI/MiniMax-M3:novita"
GLM_52_MODEL_ID = "zai-org/GLM-5.2:novita"
DEEPSEEK_V4_PRO_MODEL_ID = "deepseek-ai/DeepSeek-V4-Pro:novita"

HOSTED_MODEL_IDS = {
    CLAUDE_OPUS_48_MODEL_ID,
    GPT_55_MODEL_ID,
    KIMI_K27_CODE_MODEL_ID,
    MINIMAX_M3_MODEL_ID,
    GLM_52_MODEL_ID,
    DEEPSEEK_V4_PRO_MODEL_ID,
}

DIRECT_PROVIDER_MODEL_IDS = {
    GEMINI_MODEL_ID,
}

DIRECT_PROVIDER_PREFIXES = ("gemini/", "mistral/")


def is_known_router_model_id(model_id: str | None) -> bool:
    return bool(model_id and model_id in HOSTED_MODEL_IDS)


def is_direct_provider_model_id(model_id: str | None) -> bool:
    if not model_id:
        return False
    if model_id in DIRECT_PROVIDER_MODEL_IDS:
        return True
    return any(
        model_id.startswith(prefix) and len(model_id) > len(prefix)
        for prefix in DIRECT_PROVIDER_PREFIXES
    )


def is_known_model_id(model_id: str | None) -> bool:
    return (
        model_id == MISTRAL_MODEL_ID
        or is_known_router_model_id(model_id)
        or is_direct_provider_model_id(model_id)
    )
