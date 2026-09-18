import pytest
from pydantic import ValidationError

from quantum_agent.config import Settings
from quantum_agent.gateways import build_model_capability_registry
from quantum_agent.llm.routing import ModelTask


def test_text_override_includes_all_fallbacks_without_changing_other_transports() -> None:
    default = build_model_capability_registry(Settings(_env_file=None))
    registry = build_model_capability_registry(Settings(
        _env_file=None, USTC_TEXT_MODEL_OVERRIDE="deepseek-v4-flash",
        USTC_TEXT_THINKING_MODE="disabled",
    ))
    for task in (ModelTask.REASONING, ModelTask.DIAGNOSIS, ModelTask.LIGHTWEIGHT,
                 ModelTask.DOCUMENT_REASONING, ModelTask.CODE):
        profiles = registry.profiles_for(task)
        assert len(profiles) == 1
        assert profiles[0].thinking_mode == "disabled"
        assert profiles[0].provider_model == "deepseek-v4-flash"
    for task in (ModelTask.VISION, ModelTask.EMBEDDING, ModelTask.RERANK,
                 ModelTask.DOCUMENT_PARSING):
        assert registry.profiles_for(task) == default.profiles_for(task)
    assert "deepseek" not in str(registry.public_catalog())


@pytest.mark.parametrize("value", ["", " ", " model ", "model name"])
def test_override_rejects_invalid_names(value: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, USTC_TEXT_MODEL_OVERRIDE=value)
