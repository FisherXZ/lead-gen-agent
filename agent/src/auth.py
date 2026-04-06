"""JWT authentication for Supabase Auth."""

from __future__ import annotations

import os

import jwt
from fastapi import HTTPException, Request
from jwt import PyJWKClient

# Cache the JWKS client so we don't re-fetch keys on every request.
_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    """Return a cached PyJWKClient pointed at the Supabase JWKS endpoint."""
    global _jwks_client
    if _jwks_client is None:
        supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        if not supabase_url:
            raise HTTPException(status_code=500, detail="SUPABASE_URL not configured")
        jwks_url = f"{supabase_url}/auth/v1/.well-known/jwks.json"
        _jwks_client = PyJWKClient(jwks_url, cache_keys=True)
    return _jwks_client


def verify_token(request: Request) -> dict:
    """Extract and verify the Supabase JWT from the Authorization header.

    Returns the decoded token payload (contains 'sub' = user_id).
    Supports both ES256 (new Supabase projects) and HS256 (legacy).
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header[7:]  # Strip "Bearer "

    # Peek at the token header to determine the algorithm
    try:
        header = jwt.get_unverified_header(token)
    except jwt.DecodeError:
        raise HTTPException(status_code=401, detail="Malformed token") from None

    alg = header.get("alg", "")

    try:
        if alg == "HS256":
            # Legacy: symmetric secret
            secret = os.environ.get("SUPABASE_JWT_SECRET")
            if not secret:
                raise HTTPException(status_code=500, detail="SUPABASE_JWT_SECRET not configured")
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
        else:
            # ES256 / asymmetric: fetch public key from JWKS endpoint
            client = _get_jwks_client()
            signing_key = client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256"],
                audience="authenticated",
            )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired") from None
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}") from e


def _extract_user_id(payload: dict) -> str:
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing user ID")
    return user_id


def get_user_id(request: Request) -> str:
    """Extract and return the user_id (sub) from the JWT."""
    return _extract_user_id(verify_token(request))


def get_user_role(request: Request) -> str:
    """Extract the user_role from the JWT claims (injected by custom access token hook)."""
    return verify_token(request).get("user_role", "member")


def require_admin(request: Request) -> str:
    """Require admin role. Returns user_id if admin, raises 403 otherwise."""
    payload = verify_token(request)
    if payload.get("user_role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return _extract_user_id(payload)
