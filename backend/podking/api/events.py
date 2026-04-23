from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from podking.deps import current_user, get_db
from podking.models import Job, User
from podking.pubsub import subscribe, unsubscribe

router = APIRouter()

TERMINAL = {"done", "failed"}


@router.get("/events/{job_id}")
async def job_events(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> StreamingResponse:
    job = await db.get(Job, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="job not found")

    async def generate() -> AsyncIterator[str]:
        # Send current state first (handles reconnects)
        current = {
            "status": job.status,
            "progress_pct": job.progress_pct,
            "progress_message": job.progress_message,
            "error": job.error,
        }
        yield f"data: {json.dumps(current)}\n\n"

        if job.status in TERMINAL:
            return

        q = subscribe(job_id)
        try:
            while True:
                event = await q.get()
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("status") in TERMINAL:
                    break
        finally:
            unsubscribe(job_id, q)

    return StreamingResponse(generate(), media_type="text/event-stream")
