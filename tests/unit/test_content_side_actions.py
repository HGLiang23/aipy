"""Coverage for the real model gateway and the export/collect/assign routing.

These are pure (no database): gateway selection, the OpenAI adapter with a mocked
client, and the constants that steer side-effect actions away from the state machine.
"""

from typing import Any

import openai
import pytest
from pydantic import SecretStr

from aipy.modules.llm import (
    HttpModelGateway,
    ModelRequest,
    StubModelGateway,
    select_gateway,
)
from aipy.shared.config import AppSettings, LlmSettings
from apps.api import repositories


def test_select_gateway_local_without_config_uses_stub() -> None:
    gateway = select_gateway(AppSettings(environment="local"))
    assert isinstance(gateway, StubModelGateway)


def test_select_gateway_configured_uses_http() -> None:
    settings = AppSettings(
        environment="local",
        llm=LlmSettings(base_url="http://llm", api_key=SecretStr("k"), model="m"),
    )
    assert settings.llm_configured
    assert isinstance(select_gateway(settings), HttpModelGateway)


def test_select_gateway_staging_without_config_raises() -> None:
    with pytest.raises(RuntimeError):
        select_gateway(AppSettings(environment="staging"))


def test_http_gateway_completes_with_mocked_client(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeMessage:
        content = "生成的真实内容"

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **_kwargs: Any) -> FakeResponse:
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(openai, "OpenAI", lambda *a, **k: FakeClient(), raising=True)

    gateway = HttpModelGateway(
        LlmSettings(base_url="http://llm", api_key=SecretStr("k"), model="m")
    )
    result = gateway.complete(ModelRequest(prompt="写一段", system="助手"))
    assert result.text == "生成的真实内容"


def test_side_effect_actions_route_outside_state_machine() -> None:
    # Side effects must not be treated as state transitions.
    assert "collect" not in repositories.SUPPORTED_ACTIONS["content"]
    assert "export" not in repositories.SUPPORTED_ACTIONS["content"]
    assert "assign" not in repositories.SUPPORTED_ACTIONS["review"]

    assert "collect" in repositories.CONTENT_SIDE_EFFECTS
    assert "export" in repositories.CONTENT_SIDE_EFFECTS
    assert "assign" in repositories.REVIEW_SIDE_EFFECTS

    # And the authorization catalogue must offer them so the board shows buttons.
    assert "content:collect" in repositories.CANDIDATE_ACTIONS["content"]
    assert "review:assign" in repositories.CANDIDATE_ACTIONS["review"]
