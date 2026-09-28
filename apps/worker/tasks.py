"""Asynchronous content workflow execution.

When an API action (re)starts a content run, the HTTP handler flips its status to
RUNNING and enqueues :func:`run_content_workflow`. This task performs the
(simulated) generation through a :class:`~aipy.modules.llm.ModelGateway` and writes
the terminal status back via the same state-machine labels the API uses, so the
board stays consistent whether a run finishes in-process or on a worker.

Each write opens its own tenant-scoped session and commits, so a failure mid-run
leaves the row in whatever state the last committed write set (RUNNING) rather
than an open transaction that the broker would time out.
"""

import logging
from uuid import UUID

from celery.exceptions import OperationalError as CeleryOperationalError
from kombu.exceptions import OperationalError as KombuOperationalError
from sqlalchemy import select

from aipy.modules.content.models import ContentRun
from aipy.modules.content.state_machine import content_status_label
from aipy.modules.llm import ModelGateway, ModelRequest, select_gateway
from aipy.shared.config import get_settings
from aipy.shared.db import SessionFactory, make_engine, make_session_factory, tenant_session_scope

from .celery_app import celery_app

logger = logging.getLogger(__name__)

_TERMINAL = frozenset({"COMPLETED", "CANCELLED"})


def _build_request(row: ContentRun) -> ModelRequest:
    return ModelRequest(
        system="AI 写作助手",
        prompt=f"请基于品牌「{row.brand}」完成《{row.title}》的写作，当前阶段：{row.stage_label}。",
    )


def _apply_status(row: ContentRun, status: str) -> None:
    """Pure status writeback shared by the worker and the unit tests.

    Only the machine-owned display columns are touched here; ``updated_by`` is set
    by the DB wrapper so the same helper serves both paths.
    """

    label, tone = content_status_label(status)
    row.status = status
    row.status_label = label
    row.tone = tone
    row.updated_at_label = "刚刚"


def _set_status(
    factory: SessionFactory, tenant_id: UUID, run_code: str, status: str, actor_id: UUID
) -> None:
    with tenant_session_scope(factory, tenant_id) as session:
        row = (
            session.execute(select(ContentRun).where(ContentRun.code == run_code)).scalars().first()
        )
        if row is None:
            return
        _apply_status(row, status)
        row.updated_by = actor_id
        session.flush()


def _load_status(factory: SessionFactory, tenant_id: UUID, run_code: str) -> str | None:
    with tenant_session_scope(factory, tenant_id) as session:
        row = (
            session.execute(select(ContentRun).where(ContentRun.code == run_code)).scalars().first()
        )
        return row.status if row is not None else None


_factory: SessionFactory | None = None


def _get_factory() -> SessionFactory:
    global _factory
    if _factory is None:
        settings = get_settings()
        _factory = make_session_factory(make_engine(settings.database.url))
    return _factory


@celery_app.task(name="content.run.execute", max_retries=2)  # type: ignore[untyped-decorator]
def run_content_workflow(run_code: str, tenant_id: str, actor_id: str) -> str:
    """Generate a content run and write back its terminal status.

    Returns a short outcome token (``completed`` / ``failed:<Exc>`` / ``not_found``
    / ``skipped_terminal``) so a monitoring dashboard can trace runs without
    parsing logs.
    """

    tid = UUID(tenant_id)
    aid = UUID(actor_id)
    factory = _get_factory()

    current = _load_status(factory, tid, run_code)
    if current is None:
        return "not_found"
    if current in _TERMINAL:
        return "skipped_terminal"

    _set_status(factory, tid, run_code, "RUNNING", aid)

    try:
        with tenant_session_scope(factory, tid) as session:
            row = (
                session.execute(select(ContentRun).where(ContentRun.code == run_code))
                .scalars()
                .first()
            )
            if row is None:
                return "not_found"
            request = _build_request(row)
        gateway: ModelGateway = select_gateway(get_settings())
        result = gateway.complete(request)
        with tenant_session_scope(factory, tid) as session:
            row = (
                session.execute(select(ContentRun).where(ContentRun.code == run_code))
                .scalars()
                .first()
            )
            if row is not None:
                row.content = result.text
        _set_status(factory, tid, run_code, "COMPLETED", aid)
        return "completed"
    except Exception as exc:  # noqa: BLE001 - record failure, do not crash the broker
        _set_status(factory, tid, run_code, "FAILED", aid)
        return f"failed:{type(exc).__name__}"


def enqueue_content_run(run_code: str, tenant_id: UUID, actor_id: UUID) -> None:
    """Fire-and-forget hand-off from the API after a (re)start action.

    A missing broker (e.g. local dev without Redis) must not turn a successful
    state transition into a 500: the run stays in RUNNING and the operator sees a
    warning instead of a broken click.
    """

    try:
        run_content_workflow.delay(run_code, str(tenant_id), str(actor_id))
    except (CeleryOperationalError, KombuOperationalError):
        logger.warning(
            "celery broker unreachable; run %s stays in RUNNING without async execution", run_code
        )
