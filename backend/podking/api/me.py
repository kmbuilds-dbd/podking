import secrets

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from podking.config import get_settings
from podking.deps import current_user, get_db
from podking.models import User

router = APIRouter(prefix="/api")


@router.get("/me")
async def me(user: User = Depends(current_user)) -> dict[str, str | None]:
    return {"email": user.email, "display_name": user.display_name}


def _new_feed_token() -> str:
    # 32 url-safe chars (~190 bits of entropy). Long enough to be a
    # bearer secret in a URL, short enough to be readable when copied.
    return secrets.token_urlsafe(24)


def _build_reader_base(request: Request, token: str) -> str:
    base = get_settings().app_base_url.rstrip("/")
    return f"{base}/reader/{token}"


async def _ensure_token(db: AsyncSession, user: User) -> str:
    if user.feed_token:
        return user.feed_token
    user.feed_token = _new_feed_token()
    await db.commit()
    await db.refresh(user)
    assert user.feed_token is not None
    return user.feed_token


@router.get("/me/feed-url")
async def get_feed_url(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, str]:
    """Return the user's reader link base URL. Lazily creates the token
    on first request so existing users don't need a backfill migration."""
    token = await _ensure_token(db, user)
    return {
        "token": token,
        "base_url": _build_reader_base(request, token),
    }


@router.post("/me/feed-url/regenerate")
async def regenerate_feed_url(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, str]:
    """Rotate the user's reader token, invalidating any links already
    copied or shared."""
    user.feed_token = _new_feed_token()
    await db.commit()
    await db.refresh(user)
    assert user.feed_token is not None
    return {
        "token": user.feed_token,
        "base_url": _build_reader_base(request, user.feed_token),
    }
