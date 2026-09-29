"""Worker task registration, status writeback, and broker-resilience.

These checks need no database or broker: the DB round-trip is covered by the
CI PostgreSQL service, while the broker-down path is exercised here by faking
``delay`` so a missing Redis never breaks an API (re)start in local dev.
"""

from uuid import uuid4

import pytest
from kombu.exceptions import OperationalError as KombuOperationalError

from apps.worker.tasks import _TERMINAL, _apply_status, enqueue_content_run, run_content_workflow


class _FakeRow:
    status = ""
    status_label = ""
    tone = ""
    updated_at_label = ""


def test_task_is_registered_under_stable_name() -> None:
    assert run_content_workflow.name == "content.run.execute"


def test_terminal_set_covers_finished_states() -> None:
    assert "COMPLETED" in _TERMINAL
    assert "CANCELLED" in _TERMINAL


def test_apply_status_writes_machine_fields() -> None:
    row = _FakeRow()
    _apply_status(row, "COMPLETED")

    assert row.status == "COMPLETED"
    assert row.status_label == "已完成"
    assert row.tone == "success"
    assert row.updated_at_label == "刚刚"


def test_enqueue_is_resilient_when_broker_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, tuple[str, str, str]] = {}

    def fake_delay(run_code: str, tenant_id: str, actor_id: str) -> None:
        captured["args"] = (run_code, tenant_id, actor_id)
        raise KombuOperationalError("broker down")

    monkeypatch.setattr(run_content_workflow, "delay", fake_delay)

    # Must not raise: a missing broker turns into a warning, not a 500.
    enqueue_content_run("CR-1", uuid4(), uuid4())

    assert captured["args"][0] == "CR-1"
