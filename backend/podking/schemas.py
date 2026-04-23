from pydantic import BaseModel


class KeyStatus(BaseModel):
    set: bool


class SettingsResponse(BaseModel):
    system_prompt: str
    anthropic_key: KeyStatus
    elevenlabs_key: KeyStatus
    voyage_key: KeyStatus


class SettingsPatch(BaseModel):
    system_prompt: str | None = None
    anthropic_api_key: str | None = None
    elevenlabs_api_key: str | None = None
    voyage_api_key: str | None = None
