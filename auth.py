# auth.py
import os, json, uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from fastapi import Depends, HTTPException, status, Request
from fastapi import Path as FPath
from fastapi.security import HTTPBasic, HTTPBasicCredentials, HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from pydantic import BaseModel

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
# Allowed clients: username -> password
_CLIENTS_RAW = os.getenv("PDF_API_CLIENTS", '{"demo":"demo"}')
try:
    CLIENTS: Dict[str, str] = json.loads(_CLIENTS_RAW)
except json.JSONDecodeError:
    CLIENTS = {"demo": "demo"}

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("PDF_API_TOKEN_TTL_MIN", "60"))
JWT_SECRET = os.getenv("PDF_API_JWT_SECRET", "CHANGE_ME_IN_PROD")
JWT_ALG = "HS256"

# -----------------------------------------------------------------------------
# In-memory sessions: session_id -> { client_id, expires_at }
# (kept to preserve your workspace per session and allow session extension)
# -----------------------------------------------------------------------------
SESSIONS: Dict[str, Dict] = {}

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _bump_expiry() -> datetime:
    return _now_utc() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

def _new_session_id() -> str:
    return str(uuid.uuid4())

# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------
class HandshakeResponse(BaseModel):
    session_id: str
    expires_at: datetime
    access_token: str
    token_type: str = "bearer"

# -----------------------------------------------------------------------------
# Security helpers
# -----------------------------------------------------------------------------
basic_scheme  = HTTPBasic(auto_error=False)    # allow missing; we'll fallback to bearer
bearer_scheme = HTTPBearer(auto_error=False)   # allow missing; we'll fallback to basic

def _verify_basic(credentials: Optional[HTTPBasicCredentials]) -> Optional[str]:
    """
    Returns client_id if Basic is present & valid; else None.
    """
    if not credentials:
        return None
    client_id = credentials.username or ""
    password  = credentials.password or ""
    expected  = CLIENTS.get(client_id)
    if expected is None or expected != password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return client_id

def _create_jwt(client_id: str, session_id: str, minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES) -> str:
    payload = {
        "sub": client_id,
        "sid": session_id,
        "exp": _now_utc() + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def _verify_jwt(creds: Optional[HTTPAuthorizationCredentials]) -> Optional[dict]:
    """
    Returns payload if Bearer is present & valid; else None.
    """
    if not creds or not creds.scheme or creds.scheme.lower() != "bearer":
        return None
    token = creds.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        # must contain sub and sid
        if not payload.get("sub") or not payload.get("sid"):
            raise HTTPException(status_code=401, detail="Invalid token payload")
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

# -----------------------------------------------------------------------------
# Public: Handshake (Basic) -> session_id + JWT
# -----------------------------------------------------------------------------
async def handshake_basic(
    basic: Optional[HTTPBasicCredentials] = Depends(basic_scheme),
) -> HandshakeResponse:
    client_id = _verify_basic(basic)  # requires Basic creds
    session_id = _new_session_id()
    expires_at = _bump_expiry()
    SESSIONS[session_id] = {"client_id": client_id, "expires_at": expires_at}
    token = _create_jwt(client_id, session_id)
    return HandshakeResponse(session_id=session_id, expires_at=expires_at, access_token=token)

# -----------------------------------------------------------------------------
# Public: Extend (Basic) -> extend session TTL and return a fresh JWT
# -----------------------------------------------------------------------------
async def extend_session(
    session_id: str = FPath(...),
    basic: Optional[HTTPBasicCredentials] = Depends(basic_scheme),
) -> HandshakeResponse:
    client_id = _verify_basic(basic)  # requires Basic creds
    sess = SESSIONS.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    if sess["client_id"] != client_id:
        raise HTTPException(status_code=403, detail="Session does not belong to this client")
    sess["expires_at"] = _bump_expiry()
    token = _create_jwt(client_id, session_id)
    return HandshakeResponse(session_id=session_id, expires_at=sess["expires_at"], access_token=token)

# -----------------------------------------------------------------------------
# Dependency: Accepts EITHER Bearer JWT OR Basic+session.
#   - If Bearer present → verify JWT, check sid == path, allow (no session lookup needed)
#   - Else Basic → verify Basic, check in-memory session and sliding TTL
# -----------------------------------------------------------------------------
async def require_auth_simple(
    session_id: str = FPath(..., description="Session ID from path"),
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    basic:  Optional[HTTPBasicCredentials]        = Depends(basic_scheme),
):
    # 1) Prefer Bearer JWT if present
    if bearer and bearer.credentials:
        payload = _verify_jwt(bearer)   # raises 401 if invalid
        if payload["sid"] != session_id:
            raise HTTPException(status_code=403, detail="Session mismatch for token")
        # OK: JWT is stateless; no session bump. (Workspace is still session_id-based.)
        return {"client_id": payload["sub"], "session_id": session_id, "auth": "bearer"}

    # 2) Fallback to Basic + session store
    client_id = _verify_basic(basic)  # raises 401 if invalid/missing
    sess = SESSIONS.get(session_id)
    if not sess:
        raise HTTPException(status_code=401, detail="Invalid or expired session; run /auth/handshake")
    if sess["client_id"] != client_id:
        raise HTTPException(status_code=403, detail="Session does not belong to this client")
    if _now_utc() >= sess["expires_at"]:
        raise HTTPException(status_code=401, detail="Session expired; call /auth/extend or /auth/handshake")
    # sliding TTL for Basic path
    sess["expires_at"] = _bump_expiry()
    return {"client_id": client_id, "session_id": session_id, "auth": "basic"}
