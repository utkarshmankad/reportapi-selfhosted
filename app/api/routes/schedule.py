"""Schedule CRUD routes — powers the config UI's schedule form."""
from uuid import UUID
from croniter import croniter
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.schedule import CreateScheduleRequest, ScheduleResponse
from app.db.session import get_db
from app.db.models import Schedule

router = APIRouter(prefix="/api/schedule", tags=["schedule"])


@router.post("", response_model=ScheduleResponse)
async def create_schedule(request: CreateScheduleRequest, db: AsyncSession = Depends(get_db)):
    if not croniter.is_valid(request.cron_expression):
        raise HTTPException(status_code=422, detail="cron_expression is not a valid cron string")

    if not request.board_id and not request.sprint_id:
        raise HTTPException(status_code=422, detail="Either board_id or sprint_id is required")

    schedule = Schedule(
        connector=request.connector,
        board_id=request.board_id,
        sprint_id=request.sprint_id,
        cron_expression=request.cron_expression,
        output_format=request.output_format,
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    return schedule


@router.get("", response_model=list[ScheduleResponse])
async def list_schedules(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Schedule).order_by(Schedule.created_at.desc()))
    return result.scalars().all()


@router.delete("/{schedule_id}", status_code=204)
async def delete_schedule(schedule_id: UUID, db: AsyncSession = Depends(get_db)):
    schedule = await db.get(Schedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    await db.delete(schedule)
    await db.commit()
