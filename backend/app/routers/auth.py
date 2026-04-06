"""
Amazon OAuth 2.0 (Login with Amazon) flow.
"""
import logging
import secrets
import urllib.parse
from datetime import datetime, timezone, timedelta

import httpx
from fastapi import APIRouter, Request, Response, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models.user import User
from ..services.crypto import encrypt, decrypt

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/auth", tags=["auth"])

LWA_AUTH_URL = "https://www.amazon.com/ap/oa"
LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"
LWA_PROFILE_URL = "https://api.amazon.com/user/profile"


@router.get("/login")
async def login(request: Request):
    """Redirect user to Amazon's OAuth consent screen."""
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state

    params = {
        "client_id": settings.AMAZON_CLIENT_ID,
        "scope": settings.AMAZON_OAUTH_SCOPES,
        "response_type": "code",
        "redirect_uri": settings.AMAZON_OAUTH_REDIRECT_URI,
        "state": state,
    }
    url = LWA_AUTH_URL + "?" + urllib.parse.urlencode(params)
    return RedirectResponse(url)


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    if error:
        logger.warning("OAuth error: %s", error)
        return RedirectResponse(f"{settings.APP_PATH_PREFIX}/?error=login_failed")

    stored_state = request.session.get("oauth_state")
    if not state or state != stored_state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            LWA_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.AMAZON_OAUTH_REDIRECT_URI,
                "client_id": settings.AMAZON_CLIENT_ID,
                "client_secret": settings.AMAZON_CLIENT_SECRET,
            },
        )
        if token_resp.status_code != 200:
            logger.error("Token exchange failed: %s", token_resp.text)
            return RedirectResponse(f"{settings.APP_PATH_PREFIX}/?error=token_failed")

        tokens = token_resp.json()
        access_token = tokens.get("access_token", "")
        refresh_token = tokens.get("refresh_token", "")
        expires_in = tokens.get("expires_in", 3600)

        # Fetch user profile
        profile_resp = await client.get(
            LWA_PROFILE_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if profile_resp.status_code != 200:
            logger.error("Profile fetch failed: %s", profile_resp.text)
            return RedirectResponse(f"{settings.APP_PATH_PREFIX}/?error=profile_failed")

        profile = profile_resp.json()

    user_id = profile.get("user_id", "")
    email = profile.get("email", "")
    name = profile.get("name", "")
    postal_code = profile.get("postal_code", "")

    # Upsert user with encrypted tokens
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        user = User(id=user_id)
        db.add(user)

    user.name = name
    user.postal_code = postal_code
    user.encrypted_email = encrypt(email) if email else None
    user.encrypted_access_token = encrypt(access_token) if access_token else None
    user.encrypted_refresh_token = encrypt(refresh_token) if refresh_token else None
    user.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    if not user.alert_email and email:
        user.alert_email = email
    db.commit()

    # Store user session
    request.session["user_id"] = user_id
    request.session.pop("oauth_state", None)

    return RedirectResponse(f"{settings.APP_PATH_PREFIX}/dashboard")


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(f"{settings.APP_PATH_PREFIX}/")


async def refresh_user_token(user: User, db: Session) -> str | None:
    """Refresh Amazon access token using refresh token. Returns new access token."""
    if not user.encrypted_refresh_token:
        return None
    refresh_token = decrypt(user.encrypted_refresh_token)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                LWA_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": settings.AMAZON_CLIENT_ID,
                    "client_secret": settings.AMAZON_CLIENT_SECRET,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                new_token = data.get("access_token", "")
                expires_in = data.get("expires_in", 3600)
                user.encrypted_access_token = encrypt(new_token)
                user.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                db.commit()
                return new_token
    except Exception as exc:
        logger.error("Token refresh failed: %s", exc)
    return None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user
