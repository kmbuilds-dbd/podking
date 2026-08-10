from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from podking.models import PromptStyle, UserSettings


async def ensure_general_prompt_style(
    db: AsyncSession, user_id: uuid.UUID
) -> PromptStyle:
    result = await db.execute(
        select(PromptStyle).where(
            PromptStyle.user_id == user_id,
            PromptStyle.label == "general",
        )
    )
    style = result.scalar_one_or_none()
    if style is not None:
        return style

    settings_result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user_id)
    )
    settings = settings_result.scalar_one_or_none()
    style = PromptStyle(
        user_id=user_id,
        label="general",
        prompt_text=settings.system_prompt if settings is not None else "",
    )
    db.add(style)
    await db.flush()
    return style
