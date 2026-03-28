from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.routes import _get_current_user
from db.config import get_session
from db.models import OAuthToken, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/email", tags=["email"])

# ---------- Google (Gmail) ----------

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_SCOPES = "openid email https://www.googleapis.com/auth/gmail.readonly"


def _google_creds() -> tuple[str, str]:
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth not configured",
        )
    return client_id, client_secret


@router.get("/gmail/authorize")
async def gmail_authorize(
    redirect_uri: str = Query(...),
    user: User = Depends(_get_current_user),
):
    client_id, _ = _google_creds()
    state = f"{user.id}:{uuid.uuid4().hex}"
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GOOGLE_SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return {"authorization_url": f"{GOOGLE_AUTH_URL}?{urlencode(params)}"}


@router.get("/gmail/callback")
async def gmail_callback(
    code: str = Query(...),
    state: str = Query(""),
    redirect_uri: str = Query(...),
    user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
):
    client_id, client_secret = _google_creds()

    # Exchange authorization code for tokens
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            logger.error("Google token exchange failed: %s", token_resp.text)
            raise HTTPException(status_code=400, detail="Failed to exchange authorization code")
        tokens = token_resp.json()

        # Get user email from Google
        userinfo_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        if userinfo_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch user info from Google")
        userinfo = userinfo_resp.json()

    email_address = userinfo.get("email", "")

    # Upsert token record
    existing = await session.execute(
        select(OAuthToken).where(
            OAuthToken.user_id == user.id,
            OAuthToken.provider == "gmail",
        )
    )
    oauth_token = existing.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    expires_in = tokens.get("expires_in", 3600)
    token_expiry = datetime.fromtimestamp(now.timestamp() + expires_in, tz=timezone.utc)

    if oauth_token:
        oauth_token.access_token = tokens["access_token"]
        oauth_token.refresh_token = tokens.get("refresh_token", oauth_token.refresh_token)
        oauth_token.token_expiry = token_expiry
        oauth_token.email_address = email_address
        oauth_token.is_active = True
        oauth_token.updated_at = now
    else:
        oauth_token = OAuthToken(
            user_id=user.id,
            tenant_id=user.tenant_id,
            provider="gmail",
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token", ""),
            token_expiry=token_expiry,
            email_address=email_address,
        )
        session.add(oauth_token)

    await session.flush()

    return {
        "message": "Gmail account connected successfully",
        "email": email_address,
        "provider": "gmail",
    }


# ---------- Microsoft (Outlook) ----------

MICROSOFT_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
MICROSOFT_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
MICROSOFT_USERINFO_URL = "https://graph.microsoft.com/v1.0/me"
MICROSOFT_SCOPES = "openid email Mail.Read User.Read offline_access"


def _microsoft_creds() -> tuple[str, str]:
    client_id = os.environ.get("MICROSOFT_CLIENT_ID", "")
    client_secret = os.environ.get("MICROSOFT_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Microsoft OAuth not configured",
        )
    return client_id, client_secret


@router.get("/outlook/authorize")
async def outlook_authorize(
    redirect_uri: str = Query(...),
    user: User = Depends(_get_current_user),
):
    client_id, _ = _microsoft_creds()
    state = f"{user.id}:{uuid.uuid4().hex}"
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": MICROSOFT_SCOPES,
        "state": state,
    }
    return {"authorization_url": f"{MICROSOFT_AUTH_URL}?{urlencode(params)}"}


@router.get("/outlook/callback")
async def outlook_callback(
    code: str = Query(...),
    state: str = Query(""),
    redirect_uri: str = Query(...),
    user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
):
    client_id, client_secret = _microsoft_creds()

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            MICROSOFT_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            logger.error("Microsoft token exchange failed: %s", token_resp.text)
            raise HTTPException(status_code=400, detail="Failed to exchange authorization code")
        tokens = token_resp.json()

        # Get user email from Microsoft Graph
        userinfo_resp = await client.get(
            MICROSOFT_USERINFO_URL,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        if userinfo_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch user info from Microsoft")
        userinfo = userinfo_resp.json()

    email_address = userinfo.get("mail") or userinfo.get("userPrincipalName", "")

    # Upsert token record
    existing = await session.execute(
        select(OAuthToken).where(
            OAuthToken.user_id == user.id,
            OAuthToken.provider == "outlook",
        )
    )
    oauth_token = existing.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    expires_in = tokens.get("expires_in", 3600)
    token_expiry = datetime.fromtimestamp(now.timestamp() + expires_in, tz=timezone.utc)

    if oauth_token:
        oauth_token.access_token = tokens["access_token"]
        oauth_token.refresh_token = tokens.get("refresh_token", oauth_token.refresh_token)
        oauth_token.token_expiry = token_expiry
        oauth_token.email_address = email_address
        oauth_token.is_active = True
        oauth_token.updated_at = now
    else:
        oauth_token = OAuthToken(
            user_id=user.id,
            tenant_id=user.tenant_id,
            provider="outlook",
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token", ""),
            token_expiry=token_expiry,
            email_address=email_address,
        )
        session.add(oauth_token)

    await session.flush()

    return {
        "message": "Outlook account connected successfully",
        "email": email_address,
        "provider": "outlook",
    }
