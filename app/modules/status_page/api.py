from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request

from app.core.auth.dependencies import require_dashboard_admin_access, set_dashboard_error_format
from app.core.exceptions import DashboardPermissionError
from app.dependencies import StatusPageContext, get_status_page_context
from app.modules.status_page.assistant_schemas import (
    AssistantConfigurationResponse,
    AssistantConfigurationUpdate,
    AssistantConnectionTest,
)
from app.modules.status_page.guide_schemas import GuideListResponse, GuideRecord, GuideRevision, GuideWrite
from app.modules.status_page.schemas import (
    AnnouncementSaved,
    AnnouncementUpdate,
    EmailConfigurationResponse,
    EmailConfigurationUpdate,
    StatusPageSettingsResponse,
)


def require_same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if (
        request.method in {"POST", "PUT", "DELETE", "PATCH"}
        and origin
        and urlsplit(origin).netloc != request.headers.get("host")
    ):
        raise DashboardPermissionError("Cross-origin status-page updates are not allowed")


router = APIRouter(
    prefix="/api/settings/status-page",
    tags=["dashboard"],
    dependencies=[
        Depends(set_dashboard_error_format),
        Depends(require_dashboard_admin_access),
        Depends(require_same_origin),
    ],
)


@router.get("", response_model=StatusPageSettingsResponse)
async def get_status_page(ctx: StatusPageContext = Depends(get_status_page_context)) -> StatusPageSettingsResponse:
    return await ctx.service.get_settings()


@router.put("/email", response_model=EmailConfigurationResponse)
async def update_email(
    payload: EmailConfigurationUpdate, ctx: StatusPageContext = Depends(get_status_page_context)
) -> EmailConfigurationResponse:
    return await ctx.service.update_email(payload)


@router.post("/announcements", response_model=AnnouncementSaved, status_code=201)
async def create_announcement(
    payload: AnnouncementUpdate, ctx: StatusPageContext = Depends(get_status_page_context)
) -> AnnouncementSaved:
    return await ctx.service.save_announcement(payload)


@router.put("/announcements/{notice_id}", response_model=AnnouncementSaved)
async def update_announcement(
    notice_id: int, payload: AnnouncementUpdate, ctx: StatusPageContext = Depends(get_status_page_context)
) -> AnnouncementSaved:
    return await ctx.service.save_announcement(payload, notice_id)


@router.get("/guides", response_model=GuideListResponse)
async def list_guides(ctx: StatusPageContext = Depends(get_status_page_context)) -> GuideListResponse:
    return await ctx.service.list_guides()


@router.post("/guides", response_model=GuideRecord, status_code=201)
async def create_guide(payload: GuideWrite, ctx: StatusPageContext = Depends(get_status_page_context)) -> GuideRecord:
    return await ctx.service.save_guide(payload)


@router.put("/guides/{guide_id}", response_model=GuideRecord)
async def update_guide(
    guide_id: int, payload: GuideWrite, ctx: StatusPageContext = Depends(get_status_page_context)
) -> GuideRecord:
    return await ctx.service.save_guide(payload, guide_id)


@router.delete("/guides/{guide_id}", response_model=GuideRecord)
async def delete_guide(
    guide_id: int, payload: GuideRevision, ctx: StatusPageContext = Depends(get_status_page_context)
) -> GuideRecord:
    return await ctx.service.delete_guide(guide_id, payload)


@router.post("/guides/{guide_id}/restore", response_model=GuideRecord)
async def restore_guide(
    guide_id: int, payload: GuideRevision, ctx: StatusPageContext = Depends(get_status_page_context)
) -> GuideRecord:
    return await ctx.service.delete_guide(guide_id, payload, restore=True)


@router.get("/assistant", response_model=AssistantConfigurationResponse)
async def get_assistant_configuration(
    ctx: StatusPageContext = Depends(get_status_page_context),
) -> AssistantConfigurationResponse:
    return await ctx.service.get_assistant_configuration()


@router.put("/assistant", response_model=AssistantConfigurationResponse)
async def update_assistant_configuration(
    payload: AssistantConfigurationUpdate,
    ctx: StatusPageContext = Depends(get_status_page_context),
) -> AssistantConfigurationResponse:
    return await ctx.service.update_assistant_configuration(payload)


@router.post("/assistant/test", response_model=AssistantConnectionTest)
async def test_assistant_connection(
    ctx: StatusPageContext = Depends(get_status_page_context),
) -> AssistantConnectionTest:
    return await ctx.service.test_assistant_connection()
