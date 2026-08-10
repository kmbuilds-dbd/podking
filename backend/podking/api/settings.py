from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from podking.crypto import encrypt
from podking.deps import current_user, get_db
from podking.models import PromptStyle, User, UserSettings
from podking.prompt_styles import ensure_general_prompt_style
from podking.schemas import KeyStatus, PromptStyleResponse, SettingsPatch, SettingsResponse

router = APIRouter(prefix="/api")


def _ensure_settings(user: User) -> UserSettings:
    if user.settings is None:
        user.settings = UserSettings(system_prompt="")
    return user.settings


async def _settings_response(db: AsyncSession, user: User) -> SettingsResponse:
    s = _ensure_settings(user)
    general = await ensure_general_prompt_style(db, user.id)
    await db.commit()
    styles_result = await db.execute(
        select(PromptStyle)
        .where(PromptStyle.user_id == user.id)
        .order_by(PromptStyle.label != "general", PromptStyle.label)
    )
    return SettingsResponse(
        system_prompt=general.prompt_text,
        prompt_styles=[
            PromptStyleResponse.model_validate(style) for style in styles_result.scalars()
        ],
        anthropic_key=KeyStatus(set=s.anthropic_api_key_encrypted is not None),
        elevenlabs_key=KeyStatus(set=s.elevenlabs_api_key_encrypted is not None),
        voyage_key=KeyStatus(set=s.voyage_api_key_encrypted is not None),
        tts_voice_a_id=s.tts_voice_a_id,
        tts_voice_b_id=s.tts_voice_b_id,
    )


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> SettingsResponse:
    return await _settings_response(db, user)


@router.patch("/settings", response_model=SettingsResponse)
async def patch_settings(
    patch: SettingsPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> SettingsResponse:
    s = _ensure_settings(user)
    if patch.system_prompt is not None:
        s.system_prompt = patch.system_prompt
        general = await ensure_general_prompt_style(db, user.id)
        general.prompt_text = patch.system_prompt
    if patch.anthropic_api_key is not None:
        s.anthropic_api_key_encrypted = encrypt(patch.anthropic_api_key)
    if patch.elevenlabs_api_key is not None:
        s.elevenlabs_api_key_encrypted = encrypt(patch.elevenlabs_api_key)
    if patch.voyage_api_key is not None:
        s.voyage_api_key_encrypted = encrypt(patch.voyage_api_key)
    if patch.tts_voice_a_id is not None:
        s.tts_voice_a_id = patch.tts_voice_a_id or None
    if patch.tts_voice_b_id is not None:
        s.tts_voice_b_id = patch.tts_voice_b_id or None
    db.add(user)
    await db.commit()
    return await _settings_response(db, user)
