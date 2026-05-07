import time
import pytest
from unittest.mock import patch, MagicMock
from auth.verify import verify_token, InvalidTokenError


def _make_payload(sub="user-123", email="a@b.com", role="authenticated", exp_offset=3600):
    return {
        "sub": sub,
        "email": email,
        "role": role,
        "aud": "authenticated",
        "iss": "https://xxx.supabase.co/auth/v1",
        "iat": int(time.time()),
        "exp": int(time.time()) + exp_offset,
    }


def test_verify_token_missing_raises():
    with pytest.raises(InvalidTokenError):
        verify_token("")


def test_verify_token_malformed_raises():
    with pytest.raises(InvalidTokenError):
        verify_token("not.a.valid.token")


def test_verify_valid_token():
    import jwt as pyjwt

    payload = _make_payload()
    secret = "test-secret-for-unit-tests-only"
    token = pyjwt.encode(payload, secret, algorithm="HS256")

    with patch("auth.verify._get_jwks_client") as mock_client:
        mock_key = MagicMock()
        mock_key.key = secret
        mock_client.return_value.get_signing_key_from_jwt.return_value = mock_key

        result = verify_token(token)
        assert result.sub == "user-123"
        assert result.email == "a@b.com"
        assert result.role == "authenticated"


def test_verify_expired_token():
    import jwt as pyjwt

    payload = _make_payload(exp_offset=-10)
    secret = "test-secret"
    token = pyjwt.encode(payload, secret, algorithm="HS256")

    with patch("auth.verify._get_jwks_client") as mock_client:
        mock_key = MagicMock()
        mock_key.key = secret
        mock_client.return_value.get_signing_key_from_jwt.return_value = mock_key

        with pytest.raises(InvalidTokenError, match="expired"):
            verify_token(token)
