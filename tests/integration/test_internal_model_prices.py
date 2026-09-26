from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ModelSourceModel
from app.db.session import SessionLocal
from app.modules.model_sources.repository import ModelSourcesRepository
from app.modules.model_sources.schemas import ModelSourceCreateRequest, ModelSourceModelInput, ModelSourceUpdateRequest
from app.modules.model_sources.service import ModelSourcesService

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def async_session(db_setup):
    async with SessionLocal() as session:
        yield session


@pytest.mark.asyncio
async def test_new_source_ignores_legacy_price_inputs_but_keeps_model_capabilities(async_session: AsyncSession) -> None:
    service = ModelSourcesService(ModelSourcesRepository(async_session))
    result = await service.create_source(
        ModelSourceCreateRequest(
            name="Internal model",
            base_url="http://127.0.0.1:9/v1",
            models=[
                ModelSourceModelInput(
                    model="internal-model",
                    input_per_1m=5.0,
                    cached_input_per_1m=1.0,
                    output_per_1m=15.0,
                    audio_per_minute=0.01,
                    context_window=8192,
                    supports_tools=True,
                )
            ],
        )
    )
    entry = result.models[0]
    assert (entry.input_per_1m, entry.cached_input_per_1m, entry.output_per_1m, entry.audio_per_minute) == (
        None,
        None,
        None,
        None,
    )
    assert entry.context_window == 8192
    assert entry.supports_tools is True


@pytest.mark.asyncio
@pytest.mark.parametrize("obsolete_inputs", [{}, {"inputPer1M": None, "outputPer1M": 99.0}])
async def test_source_edit_preserves_historical_prices_even_with_obsolete_input(
    async_session: AsyncSession, obsolete_inputs: dict[str, float | None]
) -> None:
    service = ModelSourcesService(ModelSourcesRepository(async_session))
    created = await service.create_source(
        ModelSourceCreateRequest(
            name="Legacy model source",
            base_url="http://127.0.0.1:9/v1",
            models=[ModelSourceModelInput(model="legacy-model")],
        )
    )
    old = (
        await async_session.execute(select(ModelSourceModel).where(ModelSourceModel.source_id == created.id))
    ).scalar_one()
    # Seed genuine historical data directly; new requests no longer set prices.
    old.input_per_1m = 2.5
    old.cached_input_per_1m = 0.25
    old.output_per_1m = 12.5
    old.audio_per_minute = 0.006
    await async_session.commit()

    model = ModelSourceModelInput.model_validate(
        {"model": "legacy-model", "displayName": "Renamed model", "supportsTools": True, **obsolete_inputs}
    )
    updated = await service.update_source(
        created.id,
        ModelSourceUpdateRequest(
            name="Renamed source",
            models=[model, ModelSourceModelInput(model="new-model", output_per_1m=3.0)],
        ),
    )
    historical = next(entry for entry in updated.models if entry.model == "legacy-model")
    assert (
        historical.input_per_1m,
        historical.cached_input_per_1m,
        historical.output_per_1m,
        historical.audio_per_minute,
    ) == (2.5, 0.25, 12.5, 0.006)
    assert historical.display_name == "Renamed model"
    assert historical.supports_tools is True
    assert updated.name == "Renamed source"
    assert next(entry for entry in updated.models if entry.model == "new-model").output_per_1m is None
