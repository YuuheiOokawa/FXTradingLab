"""Small shared DB accessors used by the order/risk/journal services. Kept separate
from the route handlers so services stay testable without spinning up FastAPI."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.identity import BrokerAccount
from app.db.models.journal import RiskSettings
from app.db.models.market import Instrument
from app.db.models.trading import PaperAccount


async def get_or_create_risk_settings(session: AsyncSession) -> RiskSettings:
    result = await session.execute(select(RiskSettings).limit(1))
    settings = result.scalar_one_or_none()
    if settings is None:
        settings = RiskSettings()
        session.add(settings)
        await session.commit()
        await session.refresh(settings)
    return settings


async def get_or_create_paper_account(session: AsyncSession) -> PaperAccount:
    result = await session.execute(select(PaperAccount).limit(1))
    account = result.scalar_one_or_none()
    if account is None:
        account = PaperAccount()
        session.add(account)
        await session.commit()
        await session.refresh(account)
    return account


async def get_instrument_by_symbol(session: AsyncSession, symbol: str) -> Instrument | None:
    result = await session.execute(select(Instrument).where(Instrument.symbol == symbol))
    return result.scalar_one_or_none()


async def get_or_create_broker_account(session: AsyncSession, provider: str, environment: str) -> BrokerAccount:
    """The `broker_accounts` row a LIVE order is booked against.

    Never stores the API token (docs/11_SECURITY.md) — only which provider and
    environment the connection points at, so a `practice` order can be told
    apart from a `live` one in the audit trail after the fact.
    """
    result = await session.execute(
        select(BrokerAccount).where(
            BrokerAccount.provider == provider, BrokerAccount.environment == environment
        ).limit(1)
    )
    account = result.scalar_one_or_none()
    if account is None:
        account = BrokerAccount(
            provider=provider,
            environment=environment,
            masked_account_id="****",
            display_name=f"{provider} ({environment})",
            is_active=True,
        )
        session.add(account)
        await session.commit()
        await session.refresh(account)
    return account
