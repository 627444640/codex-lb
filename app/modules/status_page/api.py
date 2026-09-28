from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request

from app.core.auth.dependencies import require_dashboard_admin_access, set_dashboard_error_format
from app.core.exceptions import DashboardPermissionError
from app.dependencies import StatusPageContext, get_status_page_context
from app.modules.status_page.schemas import (
    AnnouncementSaved,
    AnnouncementUpdate,
    EmailConfigurationResponse,
    EmailConfigurationUpdate,
    StatusPageSettingsResponse,
)


def require_same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if request.method in {"POST", "PUT"} and origin and urlsplit(origin).netloc != request.headers.get("host"):
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
