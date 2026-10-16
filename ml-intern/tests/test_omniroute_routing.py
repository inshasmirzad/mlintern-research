"""The web default must call the local OmniRoute gateway."""

from agent.core.llm_params import _resolve_llm_params
from agent.core.model_ids import is_direct_provider_model_id, is_known_model_id


def test_openai_auto_uses_gateway_key_and_base(monkeypatch) -> None:
    monkeypatch.setenv("OMNIROUTE_API_KEY", "test-gateway-key")
    monkeypatch.delenv("OMNIROUTE_BASE_URL", raising=False)
    monkeypatch.delenv("OMNIROUTE_ROUTE_MODEL", raising=False)
    params = _resolve_llm_params("openai/auto")
    assert params["model"] == "openai/auto"
    assert params["api_base"] == "http://127.0.0.1:20128/v1"
    assert params["api_key"] == "test-gateway-key"
    assert is_known_model_id("openai/auto")
    assert not is_direct_provider_model_id("openai/auto")


def test_openai_auto_supports_separate_gateway_port(monkeypatch) -> None:
    monkeypatch.setenv("OMNIROUTE_BASE_URL", "http://127.0.0.1:20129/v1")
    monkeypatch.setenv("OMNIROUTE_ROUTE_MODEL", "auto/chat:pro")
    assert _resolve_llm_params("openai/auto")["model"] == "openai/auto/chat:pro"
    assert _resolve_llm_params("openai/auto")["api_base"] == "http://127.0.0.1:20129/v1"
