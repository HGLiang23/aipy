"""ModelGateway port, stub adapter, and environment selection."""

import pytest

from aipy.modules.llm import ModelGateway, ModelRequest, StubModelGateway, select_gateway
from aipy.shared.config import AppSettings


def test_stub_gateway_echoes_the_prompt() -> None:
    out = StubModelGateway().complete(ModelRequest(prompt="写一段关于咖啡的内容"))

    assert "咖啡" in out.text
    assert "演示" in out.text


def test_stub_gateway_is_deterministic() -> None:
    gateway = StubModelGateway()
    first = gateway.complete(ModelRequest(prompt="x"))
    second = gateway.complete(ModelRequest(prompt="x"))

    assert first.text == second.text


def test_select_gateway_uses_stub_in_local_and_test() -> None:
    assert isinstance(select_gateway(AppSettings(environment="local")), StubModelGateway)
    assert isinstance(select_gateway(AppSettings(environment="test")), StubModelGateway)


def test_select_gateway_requires_real_provider_outside_local() -> None:
    with pytest.raises(RuntimeError):
        select_gateway(AppSettings(environment="staging"))


def test_base_gateway_is_not_usable() -> None:
    with pytest.raises(NotImplementedError):
        ModelGateway().complete(ModelRequest(prompt="x"))
