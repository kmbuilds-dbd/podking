from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from podking.deps import current_user, get_db
from podking.models import PromptStyle, Subscription, User, UserSettings
from podking.prompt_styles import ensure_general_prompt_style
from podking.schemas import (
    PromptStyleCreate,
    PromptStylePatch,
    PromptStyleResponse,
)

router = APIRouter(prefix="/api")


def _clean_label(label: str) -> str:
    value = label.strip()
    if not value:
        raise HTTPException(status_code=422, detail="label must not be empty")
    return value


def _clean_prompt(prompt_text: str) -> str:
    value = prompt_text.strip()
    if not value:
        raise HTTPException(status_code=422, detail="prompt_text must not be empty")
    return value


async def _get_owned_style(
    db: AsyncSession, style_id: uuid.UUID, user_id: uuid.UUID
) -> PromptStyle:
    style = await db.get(PromptStyle, style_id)
    if style is None or style.user_id != user_id:
        raise HTTPException(status_code=404, detail="prompt style not found")
    return style


async def _list_styles(db: AsyncSession, user_id: uuid.UUID) -> list[PromptStyle]:
    await ensure_general_prompt_style(db, user_id)
    await db.commit()
    result = await db.execute(
        select(PromptStyle)
        .where(PromptStyle.user_id == user_id)
        .order_by(PromptStyle.label != "general", PromptStyle.label)
    )
    return list(result.scalars())


@router.get("/prompt-styles", response_model=list[PromptStyleResponse])
async def list_prompt_styles(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> list[PromptStyleResponse]:
    return [PromptStyleResponse.model_validate(s) for s in await _list_styles(db, user.id)]


@router.post(
    "/prompt-styles",
    response_model=PromptStyleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_prompt_style(
    body: PromptStyleCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> PromptStyleResponse:
    label = _clean_label(body.label)
    prompt_text = _clean_prompt(body.prompt_text)
    if label.lower() == "general":
        raise HTTPException(status_code=409, detail="general is reserved")
    await ensure_general_prompt_style(db, user.id)
    duplicate = await db.scalar(
        select(PromptStyle).where(
            PromptStyle.user_id == user.id,
            func.lower(PromptStyle.label) == label.lower(),
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="prompt style label already exists")
    style = PromptStyle(user_id=user.id, label=label, prompt_text=prompt_text)
    db.add(style)
    await db.commit()
    await db.refresh(style)
    return PromptStyleResponse.model_validate(style)


@router.patch("/prompt-styles/{style_id}", response_model=PromptStyleResponse)
async def patch_prompt_style(
    style_id: uuid.UUID,
    body: PromptStylePatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> PromptStyleResponse:
    style = await _get_owned_style(db, style_id, user.id)
    if body.label is not None:
        label = _clean_label(body.label)
        if style.label == "general" and label != "general":
            raise HTTPException(status_code=409, detail="general cannot be renamed")
        if style.label != "general" and label.lower() == "general":
            raise HTTPException(status_code=409, detail="general is reserved")
        duplicate = await db.scalar(
            select(PromptStyle).where(
                PromptStyle.user_id == user.id,
                func.lower(PromptStyle.label) == label.lower(),
                PromptStyle.id != style.id,
            )
        )
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="prompt style label already exists")
        style.label = label
    if body.prompt_text is not None:
        style.prompt_text = _clean_prompt(body.prompt_text)
    if style.label == "general":
        if user.settings is None:
            user.settings = UserSettings(user_id=user.id, system_prompt=style.prompt_text)
        else:
            user.settings.system_prompt = style.prompt_text
    await db.commit()
    await db.refresh(style)
    return PromptStyleResponse.model_validate(style)


@router.delete("/prompt-styles/{style_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prompt_style(
    style_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> None:
    style = await _get_owned_style(db, style_id, user.id)
    if style.label == "general":
        raise HTTPException(status_code=409, detail="general cannot be deleted")
    general = await ensure_general_prompt_style(db, user.id)
    await db.execute(
        update(Subscription)
        .where(
            Subscription.user_id == user.id,
            Subscription.prompt_style_id == style.id,
        )
        .values(prompt_style_id=general.id)
    )
    await db.delete(style)
    await db.commit()
