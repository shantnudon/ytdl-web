from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ..security import RateLimiter, client_key, request_token, token_matches

router = APIRouter(prefix="/api/auth", tags=["auth"])

_login_limiter = RateLimiter(limit=8, window=300)
COOKIE_NAME = "ytdlweb_token"
COOKIE_MAX_AGE = 30 * 24 * 3600


class LoginIn(BaseModel):
    token: str = Field(min_length=1, max_length=256)


@router.get("/status")
def status(request: Request) -> dict[str, bool]:
    settings = request.app.state.settings
    if not settings.app_token:
        return {"auth_required": False, "authenticated": True}
    return {
        "auth_required": True,
        "authenticated": token_matches(request_token(request), settings.app_token),
    }


@router.post("/login")
def login(payload: LoginIn, request: Request, response: Response) -> dict[str, bool]:
    settings = request.app.state.settings
    if not settings.app_token:
        return {"ok": True, "auth_required": False}
    if not _login_limiter.allow(client_key(request)):
        raise HTTPException(status_code=429, detail="too many attempts, try again later")
    if not token_matches(payload.token, settings.app_token):
        raise HTTPException(status_code=401, detail="invalid token")
    response.set_cookie(
        COOKIE_NAME,
        payload.token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="strict",
        path="/",
    )
    return {"ok": True, "auth_required": True}


@router.post("/logout")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}
