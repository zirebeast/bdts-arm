"""Генерация realm-bdts.json из ролевой модели бэкенда (app.permissions).
Запуск: python infra/keycloak/gen_realm.py; адреса веб-клиента — из PUBLIC_URLS (через запятую), иначе адреса тестового стенда."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.permissions import DEV_USERS, ROLES  # noqa: E402

HOSTS = [h.strip() for h in os.environ.get("PUBLIC_URLS", "https://37-235-241-108.sslip.io,https://arm.gmtry.pw").split(",") if h.strip()] + ["http://localhost:5173"]


def attr_mapper(name: str) -> dict:
    return {"name": name, "protocol": "openid-connect", "protocolMapper": "oidc-usermodel-attribute-mapper", "consentRequired": False,
            "config": {"user.attribute": name, "claim.name": name, "jsonType.label": "String", "id.token.claim": "true", "access.token.claim": "true",
                       "userinfo.token.claim": "true", "introspection.token.claim": "true"}}


realm = {
    "realm": "bdts", "enabled": True, "displayName": "МП-3.5 «БДТС»",
    "displayNameHtml": "<div style='font-weight:600'>ЕЦП ДТОиР · МП-3.5 «БДТС»</div>",
    "sslRequired": "external", "registrationAllowed": False, "resetPasswordAllowed": False, "rememberMe": True, "loginWithEmailAllowed": False,
    "internationalizationEnabled": True, "supportedLocales": ["ru"], "defaultLocale": "ru",
    "accessTokenLifespan": 900, "ssoSessionIdleTimeout": 3600, "ssoSessionMaxLifespan": 36000, "bruteForceProtected": True,
    "roles": {"realm": [{"name": code, "description": r["label"]} for code, r in ROLES.items()]},
    "groups": [{"name": f"БДТС: {r['short']}", "realmRoles": [code]} for code, r in ROLES.items()],
    "clients": [{
        "clientId": "bdts-web", "name": "МП-3.5 БДТС (веб)", "enabled": True, "publicClient": True, "protocol": "openid-connect",
        "standardFlowEnabled": True, "directAccessGrantsEnabled": False, "implicitFlowEnabled": False,
        "redirectUris": [f"{h}/*" for h in HOSTS], "webOrigins": ["+"],
        "attributes": {"pkce.code.challenge.method": "S256", "post.logout.redirect.uris": "##".join(f"{h}/*" for h in HOSTS)},
        "fullScopeAllowed": True,
        "protocolMappers": [
            attr_mapper("deo"), attr_mapper("fio"), attr_mapper("position"),
            {"name": "bdts-api audience", "protocol": "openid-connect", "protocolMapper": "oidc-audience-mapper", "consentRequired": False,
             "config": {"included.custom.audience": "bdts-api", "access.token.claim": "true", "id.token.claim": "false"}},
        ],
    }],
    "users": [],
}
# Keycloak 24+: декларативный профиль пользователя; атрибуты deo/fio/position разрешены (unmanagedAttributePolicy)
_perm = {"view": ["admin", "user"], "edit": ["admin", "user"]}
_profile = {
    "attributes": [
        {"name": "username", "displayName": "${username}", "validations": {"length": {"min": 3, "max": 255}, "username-prohibited-characters": {}, "up-username-not-idn-homograph": {}}, "permissions": _perm, "multivalued": False},
        {"name": "email", "displayName": "${email}", "validations": {"email": {}, "length": {"max": 255}}, "permissions": _perm, "multivalued": False},
        {"name": "firstName", "displayName": "${firstName}", "validations": {"length": {"max": 255}}, "permissions": _perm, "multivalued": False},
        {"name": "lastName", "displayName": "${lastName}", "validations": {"length": {"max": 255}}, "permissions": _perm, "multivalued": False},
    ],
    "groups": [{"name": "user-metadata", "displayHeader": "User metadata", "displayDescription": "Attributes, which refer to user metadata"}],
    "unmanagedAttributePolicy": "ENABLED",
}
realm["components"] = {"org.keycloak.userprofile.UserProfileProvider": [
    {"providerId": "declarative-user-profile", "subComponents": {}, "config": {"kc.user.profile.config": [json.dumps(_profile, ensure_ascii=False)]}}]}
for login, u in DEV_USERS.items():
    first, *rest = (u["fio"].split(" ", 1) + [""])[:2]
    realm["users"].append({
        "username": login, "enabled": True, "emailVerified": True, "firstName": first, "lastName": rest[0] or "-",
        "email": f"{login}@bdts.local", "attributes": {"deo": [u.get("deo", "")], "fio": [u["fio"]], "position": [u.get("position", "")]},
        "credentials": [{"type": "password", "value": "${DEMO_PASSWORD}", "temporary": False}],
        "realmRoles": u["roles"], "groups": [f"/БДТС: {ROLES[r]['short']}" for r in u["roles"]],
    })
# Пользователь «demo» без группы «Просмотр»; администратор realm — отдельная учётная запись master (KEYCLOAK_ADMIN)
(Path(__file__).parent / "realm-bdts.json").write_text(json.dumps(realm, ensure_ascii=False, indent=2), encoding="utf-8")
print("realm-bdts.json:", len(realm["users"]), "users,", len(realm["roles"]["realm"]), "roles")
