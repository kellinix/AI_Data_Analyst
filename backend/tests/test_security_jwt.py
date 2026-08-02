from __future__ import annotations

import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from jose import jwk as jose_jwk
from jose import jwt

from app.core import security


def _generate_es256_keypair(kid: str) -> tuple[str, dict]:
    """Return (private_key_pem, public_jwk) for a fresh P-256 keypair."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    public_jwk = jose_jwk.construct(public_pem, algorithm="ES256").to_dict()
    public_jwk["kid"] = kid
    public_jwk["alg"] = "ES256"
    return private_pem, public_jwk


@pytest.mark.asyncio
async def test_verify_supabase_token_accepts_valid_jwks_es256_token(monkeypatch) -> None:
    """Modern Supabase projects sign access tokens with an asymmetric key
    (ES256) verified via JWKS, not the legacy shared HS256 secret. This is
    the path a real Supabase-issued token takes.
    """
    private_pem, public_jwk = _generate_es256_keypair("kid-1")
    monkeypatch.setattr(security, "_jwks_cache", {"fetched_at": time.monotonic(), "keys": [public_jwk]})
    monkeypatch.setattr(security.settings, "supabase_url", "https://example.supabase.co")

    token = jwt.encode(
        {"sub": "user-es256", "aud": "authenticated"},
        private_pem,
        algorithm="ES256",
        headers={"kid": "kid-1"},
    )

    payload = await security.verify_supabase_token(token)
    assert payload["sub"] == "user-es256"


@pytest.mark.asyncio
async def test_verify_supabase_token_rejects_es256_token_with_wrong_key(monkeypatch) -> None:
    """A token signed by a different key than the one in the (cached) JWKS
    must be rejected outright — no unverified fallback.
    """
    signing_private_pem, _ = _generate_es256_keypair("kid-1")
    _, unrelated_public_jwk = _generate_es256_keypair("kid-1")
    monkeypatch.setattr(
        security, "_jwks_cache", {"fetched_at": time.monotonic(), "keys": [unrelated_public_jwk]}
    )
    monkeypatch.setattr(security.settings, "supabase_url", "https://example.supabase.co")

    token = jwt.encode(
        {"sub": "user-es256"},
        signing_private_pem,
        algorithm="ES256",
        headers={"kid": "kid-1"},
    )

    with pytest.raises(ValueError):
        await security.verify_supabase_token(token)


@pytest.mark.asyncio
async def test_verify_supabase_token_rejects_unknown_kid(monkeypatch) -> None:
    private_pem, public_jwk = _generate_es256_keypair("kid-known")
    monkeypatch.setattr(security, "_jwks_cache", {"fetched_at": time.monotonic(), "keys": [public_jwk]})
    monkeypatch.setattr(security.settings, "supabase_url", "https://example.supabase.co")

    token = jwt.encode(
        {"sub": "user-es256"},
        private_pem,
        algorithm="ES256",
        headers={"kid": "kid-unknown"},
    )

    with pytest.raises(ValueError, match="No matching JWKS key"):
        await security.verify_supabase_token(token)


@pytest.mark.asyncio
async def test_verify_supabase_token_accepts_legacy_hs256(monkeypatch) -> None:
    """Older Supabase projects still using the shared HS256 JWT secret must
    keep working."""
    monkeypatch.setattr(security.settings, "supabase_jwt_secret", "test-shared-secret-32-characters!!")

    token = jwt.encode(
        {"sub": "user-hs256"},
        "test-shared-secret-32-characters!!",
        algorithm="HS256",
    )

    payload = await security.verify_supabase_token(token)
    assert payload["sub"] == "user-hs256"


@pytest.mark.asyncio
async def test_verify_supabase_token_rejects_hs256_without_configured_secret(monkeypatch) -> None:
    monkeypatch.setattr(security.settings, "supabase_jwt_secret", "")

    token = jwt.encode({"sub": "user-hs256"}, "some-secret", algorithm="HS256")

    with pytest.raises(ValueError, match="SUPABASE_JWT_SECRET"):
        await security.verify_supabase_token(token)


@pytest.mark.asyncio
async def test_verify_supabase_token_rejects_unsupported_algorithm(monkeypatch) -> None:
    # A malformed/garbage token whose header claims an algorithm we don't
    # support at all must fail closed, not fall through silently.
    import base64
    import json

    header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).rstrip(b"=")
    payload = base64.urlsafe_b64encode(json.dumps({"sub": "x"}).encode()).rstrip(b"=")
    token = (header + b"." + payload + b".").decode()

    with pytest.raises(ValueError, match="Unsupported Supabase token algorithm"):
        await security.verify_supabase_token(token)
