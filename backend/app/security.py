"""Аутентификация: проверка JWT Keycloak (OIDC) по JWKS. Dev-режим — только для тестов и локальной отладки."""
import logging
from functools import lru_cache

import jwt
from fastapi import Depends, Header, HTTPException, status

from app.config import get_settings
from app.permissions import DEV_USERS, CurrentUser, build_user

log = logging.getLogger(__name__)


@lru_cache
def _jwks_client() -> jwt.PyJWKClient:
    s = get_settings()
    return jwt.PyJWKClient(f"{s.oidc_internal_url}/protocol/openid-connect/certs", cache_keys=True, lifespan=3600)


def _unauthorized(msg: str = "Требуется вход в систему") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, msg, headers={"WWW-Authenticate": "Bearer"})


def decode_keycloak_token(token: str) -> CurrentUser:
    s = get_settings()
    try:
        key = _jwks_client().get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], options={"verify_aud": False})
    except jwt.PyJWTError as e:
        log.info("token rejected: %s", e)
        raise _unauthorized("Сессия истекла или токен недействителен") from e
    issuers = [i.strip() for i in s.oidc_issuers.split(",") if i.strip()]
    if issuers and claims.get("iss") not in issuers:
        raise _unauthorized("Токен выпущен другим сервером авторизации")
    aud = claims.get("aud") or []
    aud = [aud] if isinstance(aud, str) else aud
    if s.oidc_audience and s.oidc_audience not in aud and claims.get("azp") != "bdts-web":
        raise _unauthorized("Токен не предназначен для БДТС")
    roles = (claims.get("realm_access") or {}).get("roles", [])
    return build_user(
        username=claims.get("preferred_username", claims.get("sub", "")),
        fio=claims.get("fio") or claims.get("name") or claims.get("preferred_username", ""),
        roles=roles,
        deo=claims.get("deo", ""),
        position=claims.get("position", ""),
    )


def decode_dev_token(token: str) -> CurrentUser:
    username = token.removeprefix("dev:")
    u = DEV_USERS.get(username)
    if not u:
        raise _unauthorized("Неизвестный демо-пользователь")
    return build_user(username, u["fio"], u["roles"], u.get("deo", ""), u.get("position", ""))


async def get_current_user(authorization: str = Header(default="")) -> CurrentUser:
    if not authorization.lower().startswith("bearer "):
        raise _unauthorized()
    token = authorization[7:].strip()
    if get_settings().auth_mode == "dev":
        return decode_dev_token(token)
    return decode_keycloak_token(token)


def require(action: str):
    """Зависимость FastAPI: действие разрешено роли пользователя (кнопки в UI скрываются по той же матрице)."""

    async def dep(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not user.can(action):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Действие недоступно для вашей роли")
        return user

    return dep
