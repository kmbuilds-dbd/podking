from authlib.integrations.starlette_client import OAuth  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from podking.config import get_settings
from podking.deps import get_db
from podking.repositories.users import upsert_user_from_google

router = APIRouter(prefix="/auth")

oauth = OAuth()
_settings = get_settings()
oauth.register(
    name="google",
    client_id=_settings.google_client_id,
    client_secret=_settings.google_client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


@router.get("/login")
async def login(request: Request) -> Response:
    redirect_uri = get_settings().google_redirect_uri
    return await oauth.google.authorize_redirect(request, redirect_uri)  # type: ignore[no-any-return]


@router.get("/callback")
async def callback(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    token = await oauth.google.authorize_access_token(request)
    info = token.get("userinfo") or {}
    email = (info.get("email") or "").lower()
    sub = info.get("sub")
    name = info.get("name")

    if not email or not sub:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "missing Google userinfo")

    allow = get_settings().allowed_email_set
    if email not in allow:
        return HTMLResponse(
            "<h1>Access denied</h1><p>Your email is not on the allowlist.</p>",
            status_code=403,
        )

    user = await upsert_user_from_google(db, google_sub=sub, email=email, display_name=name)
    await db.commit()
    request.session["user_id"] = str(user.id)
    return RedirectResponse(url="/", status_code=302)


@router.post("/logout")
async def logout(request: Request) -> dict[str, bool]:
    request.session.clear()
    return {"ok": True}
