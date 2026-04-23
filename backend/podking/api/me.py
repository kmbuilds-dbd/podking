from fastapi import APIRouter, Depends

from podking.deps import current_user
from podking.models import User

router = APIRouter(prefix="/api")


@router.get("/me")
async def me(user: User = Depends(current_user)) -> dict[str, str | None]:
    return {"email": user.email, "display_name": user.display_name}
