# auth.py
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict

import jwt  # PyJWT
from fastapi import Depends, HTTPException, status, Header

# -------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------
# Set these via env in production
JWT_SECRET = os.getenv("PDF_API_JWT_SECRET", "change-this-in-prod")
JWT_ALG = "HS256"
JWT_EXP_HOURS = int(os.getenv("PDF_API_JWT_EXP_HOURS", "12"))

# Very simple client registry (replace with DB/SSO/etc. in prod)
# client_id -> client_secret
CLIENTS: Dict[str, str] = {
    "demo_client": "demo_secret",
    # "acme_corp": "supersecret123",
}

# -------------------------------------------------------------------
# JWT helpers
# -------------------------------------------------------------------
def create_access_token(client_id: str, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.now(tz=timezone.utc) + (expires_delta or timedelta(hours=JWT_EXP_HOURS))
    payload = {"sub": client_id, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

# -------------------------------------------------------------------
# FastAPI dependency: get current client from Bearer JWT
# -------------------------------------------------------------------
def get_current_client(authorization: Optional[str] = Header(default=None)) -> str:
    """
    Validate Authorization: Bearer <token> and return client_id (sub).
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_access_token(token)
    client_id = payload.get("sub")
    if not client_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    return client_id

# -------------------------------------------------------------------
# Handshake validator (client_id + client_secret)
# -------------------------------------------------------------------
def validate_client_credentials(client_id: str, client_secret: str) -> bool:
    expected = CLIENTS.get(client_id)
    return expected is not None and expected == client_secret
