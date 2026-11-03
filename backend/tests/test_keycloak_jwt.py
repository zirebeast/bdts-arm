"""Проверка разбора JWT Keycloak (RS256, JWKS): роли из realm_access, ДЭО из claim, проверка iss/aud."""
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from app import security
from app.config import get_settings

ISS = "https://stand1.geometry-dev.ru/auth/realms/bdts"


class _Key:
    def __init__(self, k):
        self.key = k


class _Jwks:
    def __init__(self, pub):
        self.pub = pub

    def get_signing_key_from_jwt(self, _):
        return _Key(self.pub)


@pytest.fixture
def signer(monkeypatch):
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(security, "_jwks_client", lambda: _Jwks(priv.public_key()))
    monkeypatch.setattr(get_settings(), "oidc_issuers", ISS)
    return lambda claims: jwt.encode({"iss": ISS, "exp": int(time.time()) + 300, "azp": "bdts-web", "aud": ["bdts-api", "account"], **claims}, priv, algorithm="RS256")


def test_token_roles_and_deo(signer):
    tok = signer({"preferred_username": "deo.ts", "fio": "ФИО_7", "deo": "ОРГ_9", "realm_access": {"roles": ["BDTS.OTVTS", "offline_access", "default-roles-bdts"]}})
    u = security.decode_keycloak_token(tok)
    assert u.username == "deo.ts" and u.roles == ["BDTS.OTVTS"] and u.deo == "ОРГ_9" and u.can("ts.confirm") and not u.can("task.create")


def test_token_wrong_issuer(signer):
    tok = signer({"iss": "https://evil.example/auth/realms/bdts", "preferred_username": "x", "realm_access": {"roles": []}})
    with pytest.raises(HTTPException) as e:
        security.decode_keycloak_token(tok)
    assert e.value.status_code == 401


def test_token_expired(signer):
    tok = signer({"exp": int(time.time()) - 10, "preferred_username": "x"})
    with pytest.raises(HTTPException):
        security.decode_keycloak_token(tok)
