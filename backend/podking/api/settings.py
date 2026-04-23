from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from podking.crypto import encrypt
from podking.deps import current_user, get_db
from podking.models import User, UserSettings
from podking.schemas import KeyStatus, SettingsPatch, SettingsResponse

router = APIRouter(prefix="/api")


def _ensure_settings(user: User) -> UserSettings:
    if user.settings is None:
        user.settings = UserSettings(system_prompt="")
    return user.settings


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(user: User = Depends(current_user)) -> SettingsResponse:
    s = _ensure_settings(user)
    return SettingsResponse(
        system_prompt=s.system_prompt,
        anthropic_key=KeyStatus(set=s.anthropic_api_key_encrypted is not None),
        elevenlabs_key=KeyStatus(set=s.elevenlabs_api_key_encrypted is not None),
        voyage_key=KeyStatus(set=s.voyage_api_key_encrypted is not None),
    )


@router.patch("/settings", response_model=SettingsResponse)
async def patch_settings(
    patch: SettingsPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> SettingsResponse:
    s = _ensure_settings(user)
    if patch.system_prompt is not None:
        s.system_prompt = patch.system_prompt
    if patch.anthropic_api_key is not None:
        s.anthropic_api_key_encrypted = encrypt(patch.anthropic_api_key)
    if patch.elevenlabs_api_key is not None:
        s.elevenlabs_api_key_encrypted = encrypt(patch.elevenlabs_api_key)
    if patch.voyage_api_key is not None:
        s.voyage_api_key_encrypted = encrypt(patch.voyage_api_key)
    db.add(user)
    await db.commit()
    return SettingsResponse(
        system_prompt=s.system_prompt,
        anthropic_key=KeyStatus(set=s.anthropic_api_key_encrypted is not None),
        elevenlabs_key=KeyStatus(set=s.elevenlabs_api_key_encrypted is not None),
        voyage_key=KeyStatus(set=s.voyage_api_key_encrypted is not None),
    )
