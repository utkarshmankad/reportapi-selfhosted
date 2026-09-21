"""Named report profile CRUD and generate-from-profile routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.report_service import ReportGenerationError, generate_report
from app.db.models import ReportProfile
from app.db.session import get_db
from app.models.report import GenerateReportResponse
from app.models.report_profile import (
    CreateReportProfileRequest,
    GenerateFromProfileRequest,
    ReportProfileResponse,
    UpdateReportProfileRequest,
)

router = APIRouter(prefix="/api/report-profiles", tags=["report-profiles"])


@router.post("", response_model=ReportProfileResponse)
async def create_profile(request: CreateReportProfileRequest, db: AsyncSession = Depends(get_db)):
    profile = ReportProfile(
        name=request.name,
        connector=request.connector,
        board_id=request.board_id,
        sprint_id=request.sprint_id,
        output_format=request.output_format,
        assigned_means_in_progress=request.assigned_means_in_progress,
        template_id=request.template_id,
    )
    db.add(profile)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="A profile with this name already exists"
        ) from e
    await db.refresh(profile)
    return profile


@router.get("", response_model=list[ReportProfileResponse])
async def list_profiles(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ReportProfile).order_by(ReportProfile.name))
    return result.scalars().all()


@router.get("/{profile_id}", response_model=ReportProfileResponse)
async def get_profile(profile_id: UUID, db: AsyncSession = Depends(get_db)):
    profile = await db.get(ReportProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Report profile not found")
    return profile


@router.put("/{profile_id}", response_model=ReportProfileResponse)
async def update_profile(
    profile_id: UUID, request: UpdateReportProfileRequest, db: AsyncSession = Depends(get_db)
):
    profile = await db.get(ReportProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Report profile not found")

    updates = request.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(profile, field, value)

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="A profile with this name already exists"
        ) from e
    await db.refresh(profile)
    return profile


@router.delete("/{profile_id}", status_code=204)
async def delete_profile(profile_id: UUID, db: AsyncSession = Depends(get_db)):
    profile = await db.get(ReportProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Report profile not found")
    await db.delete(profile)
    await db.commit()


@router.post("/{profile_id}/generate", response_model=GenerateReportResponse)
async def generate_from_profile(
    profile_id: UUID,
    request: GenerateFromProfileRequest,
    db: AsyncSession = Depends(get_db),
):
    profile = await db.get(ReportProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Report profile not found")

    try:
        report, ticket_count = await generate_report(
            db=db,
            connector=profile.connector,
            board_id=profile.board_id,
            sprint_id=profile.sprint_id,
            output_format=profile.output_format,
            assigned_means_in_progress=profile.assigned_means_in_progress,
            period_start=request.period_start,
            period_end=request.period_end,
            template_id=profile.template_id,
        )
    except ReportGenerationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    return GenerateReportResponse(
        report_id=report.id,
        status=report.status,
        narrative=report.narrative,
        tokens_used=report.tokens_used,
        model_used=report.model_used,
        ticket_count=ticket_count,
        output_format=report.output_format,
        is_truncated=report.is_truncated,
        truncation_reason=report.truncation_reason,
        period_start=report.period_start,
        period_end=report.period_end,
        period_semantics=report.period_semantics,
        template_id=report.template_id,
        template_version=report.template_version,
    )
