# auth.py
import os, json, uuid
from datetime import datetime, timedelta, timezone
from typing import Dict

from fastapi import Depends, HTTPException, status
from fastapi import Path as FPath
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

# ---- Config from env (very simple) -------------------------------------------
# Linux/macOS:  export PDF_API_CLIENTS='{"demo":"demo","myapp":"supersecret"}'
# Windows PS:   $env:PDF_API_CLIENTS='{"demo":"demo","myapp":"supersecret"}'
_CLIENTS_RAW = os.getenv("PDF_API_CLIENTS", '{"demo":"demo"}')
try:
    CLIENTS: Dict[str, str] = json.loads(_CLIENTS_RAW)
except json.JSONDecodeError:
    CLIENTS = {"demo": "demo"}

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("PDF_API_TOKEN_TTL_MIN", "60"))

# ---- Simple in-memory session store ------------------------------------------
# session_id -> {"client_id": str, "expires_at": datetime}
SESSIONS: Dict[str, Dict] = {}

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _new_session_id() -> str:
    return str(uuid.uuid4())

# ---- Models -------------------------------------------------------------------
class HandshakeResponse(BaseModel):
    session_id: str
    expires_at: datetime

# ---- Security (HTTP Basic) ----------------------------------------------------
basic_scheme = HTTPBasic(auto_error=True)

def _verify_basic(credentials: HTTPBasicCredentials) -> str:
    """
    Return client_id if username/password is valid, else raise 401.
    """
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

# ---- Handshake: creates a session_id with 1-hour TTL --------------------------
async def handshake_basic(credentials: HTTPBasicCredentials = Depends(basic_scheme)) -> HandshakeResponse:
    client_id = _verify_basic(credentials)
    session_id = _new_session_id()
    expires_at = _now_utc() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    SESSIONS[session_id] = {"client_id": client_id, "expires_at": expires_at}
    return HandshakeResponse(session_id=session_id, expires_at=expires_at)

# ---- Dependency used by protected endpoints -----------------------------------
async def require_basic_session(
    credentials: HTTPBasicCredentials = Depends(basic_scheme),
    session_id: str = FPath(..., description="Session ID from path"),
):
    client_id = _verify_basic(credentials)
    sess = SESSIONS.get(session_id)
    if not sess:
        raise HTTPException(status_code=401, detail="Invalid or expired session; run /auth/handshake")
    if sess["client_id"] != client_id:
        raise HTTPException(status_code=403, detail="Session does not belong to this client")
    if _now_utc() >= sess["expires_at"]:
        # optional: delete expired
        SESSIONS.pop(session_id, None)
        raise HTTPException(status_code=401, detail="Session expired; run /auth/handshake again")
    # OK → nothing to return; presence of dependency means authorized
    return {"client_id": client_id, "session_id": session_id}
