import time
import pytest
from unittest.mock import patch
import jwt as pyjwt
from auth.verify import verify_token, InvalidTokenError


_TEST_SECRET = "test-secret-for-unit-tests-only"
_TEST_ISSUER = "https://xxx.supabase.co/auth/v1"


def _make_payload(sub="user-123", email="a@b.com", role="authenticated", exp_offset=3600):
    return {
        "sub": sub,
        "email": email,
        "role": role,
        "aud": "authenticated",
        "iss": _TEST_ISSUER,
        "iat": int(time.time()),
        "exp": int(time.time()) + exp_offset,
    }


def _patch_config():
    return patch("auth.verify.AuthConfig", SUPABASE_JWT_SECRET=_TEST_SECRET, SUPABASE_URL="https://xxx.supabase.co")


def test_verify_token_missing_raises():
    with pytest.raises(InvalidTokenError):
        verify_token("")


def test_verify_token_malformed_raises():
    with pytest.raises(InvalidTokenError):
        verify_token("not.a.valid.token")


def test_verify_valid_token():
    payload = _make_payload()
    token = pyjwt.encode(payload, _TEST_SECRET, algorithm="HS256")

    with _patch_config():
        result = verify_token(token)
        assert result.sub == "user-123"
        assert result.email == "a@b.com"
        assert result.role == "authenticated"


def test_verify_expired_token():
    payload = _make_payload(exp_offset=-10)
    token = pyjwt.encode(payload, _TEST_SECRET, algorithm="HS256")

    with _patch_config():
        with pytest.raises(InvalidTokenError, match="expired"):
            verify_token(token)


def test_verify_wrong_secret():
    payload = _make_payload()
    token = pyjwt.encode(payload, "wrong-secret", algorithm="HS256")

    with _patch_config():
        with pytest.raises(InvalidTokenError):
            verify_token(token)


def test_verify_wrong_issuer():
    payload = _make_payload()
    payload["iss"] = "https://evil.supabase.co/auth/v1"
    token = pyjwt.encode(payload, _TEST_SECRET, algorithm="HS256")

    with _patch_config():
        with pytest.raises(InvalidTokenError):
            verify_token(token)
