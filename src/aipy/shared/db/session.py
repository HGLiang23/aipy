"""Synchronous engine and session factories with transaction-local tenant context."""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

SessionFactory = sessionmaker[Session]


def make_engine(database_url: str, *, echo: bool = False) -> Engine:
    return create_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
    )


def make_session_factory(engine: Engine) -> SessionFactory:
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False, autoflush=False)


def set_tenant_context(
    session: Session,
    tenant_id: UUID,
    membership_id: UUID | None = None,
) -> None:
    """Set RLS context for the current transaction only."""

    session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )
    session.execute(
        text("SELECT set_config('app.membership_id', :membership_id, true)"),
        {"membership_id": "" if membership_id is None else str(membership_id)},
    )


@contextmanager
def session_scope(factory: SessionFactory) -> Iterator[Session]:
    session = factory()
    try:
        with session.begin():
            yield session
    finally:
        session.close()


@contextmanager
def tenant_session_scope(
    factory: SessionFactory,
    tenant_id: UUID,
    membership_id: UUID | None = None,
) -> Iterator[Session]:
    with session_scope(factory) as session:
        set_tenant_context(session, tenant_id, membership_id)
        yield session
