// Аутентификация: Keycloak (OIDC Authorization Code + PKCE) или dev-режим (токен «dev:<логин>» для локальной отладки)
import { User, UserManager, WebStorageStateStore } from 'oidc-client-ts';

export interface RuntimeConfig {
  authMode: 'keycloak' | 'dev';
  oidcAuthority: string;
  oidcClientId: string;
}

let cfg: RuntimeConfig = { authMode: 'dev', oidcAuthority: '/auth/realms/bdts', oidcClientId: 'bdts-web' };
let mgr: UserManager | null = null;
let current: User | null = null;
const DEV_KEY = 'bdts.devUser';

export const DEV_USERS: [string, string][] = [
  ['demo', 'Демо: все роли'], ['gd.org', 'ФИО_1 — Организация работ'], ['gd.sogl', 'ФИО_2 — Согласование задания (ОРГ_9)'],
  ['gd.pole', 'ФИО_3 — Полевые работы (ОРГ_9)'], ['gd.kamer', 'ФИО_4 — Камеральные работы (ОРГ_9)'], ['gd.soglto', 'ФИО_5 — Согласование ТО (ОРГ_9)'],
  ['deo.to', 'ФИО_6 — Работа с ТО, ДЭО (ОРГ_9)'], ['deo.ts', 'ФИО_7 — Контроль ТС, ДЭО (ОРГ_9)'], ['gd.upload', 'ФИО_8 — Загрузка ТО'],
  ['deo.plan', 'ФИО_9 — Планирование'], ['admin', 'ФИО_10 — Администратор'], ['viewer', 'ФИО_11 — Только просмотр'],
];

export async function initAuth(): Promise<'ready' | 'login'> {
  try {
    const r = await fetch('/config.json', { cache: 'no-store' });
    if (r.ok) cfg = { ...cfg, ...(await r.json()) };
  } catch {
    /* конфигурация по умолчанию */
  }
  if (cfg.authMode === 'dev') {
    return sessionStorage.getItem(DEV_KEY) ? 'ready' : 'login';
  }
  const origin = window.location.origin;
  mgr = new UserManager({
    authority: cfg.oidcAuthority.startsWith('http') ? cfg.oidcAuthority : origin + cfg.oidcAuthority,
    client_id: cfg.oidcClientId,
    redirect_uri: `${origin}/auth-callback`,
    post_logout_redirect_uri: `${origin}/`,
    response_type: 'code',
    scope: 'openid profile',
    ui_locales: 'ru',
    automaticSilentRenew: true,
    userStore: new WebStorageStateStore({ store: window.sessionStorage }),
  });
  mgr.events.addUserLoaded((u) => { current = u; });
  mgr.events.addAccessTokenExpired(() => { current = null; });
  if (window.location.pathname === '/auth-callback') {
    const u = await mgr.signinRedirectCallback();
    current = u;
    const target = (u.state as string) || '/';
    window.history.replaceState({}, '', target);
    return 'ready';
  }
  current = await mgr.getUser();
  if (current && current.expired && current.refresh_token) {
    // продление сессии по refresh-токену (без iframe)
    try { current = await mgr.signinSilent(); } catch { current = null; }
  }
  if (!current || current.expired) {
    await mgr.signinRedirect({ state: window.location.pathname + window.location.search });
    return new Promise(() => {});
  }
  return 'ready';
}

export function authMode() {
  return cfg.authMode;
}

export function devLogin(login: string) {
  sessionStorage.setItem(DEV_KEY, login);
  window.location.reload();
}

export function getToken(): string {
  if (cfg.authMode === 'dev') return `dev:${sessionStorage.getItem(DEV_KEY) || ''}`;
  return current?.access_token || '';
}

export async function relogin() {
  if (cfg.authMode === 'dev') {
    sessionStorage.removeItem(DEV_KEY);
    window.location.reload();
    return;
  }
  await mgr?.signinRedirect({ state: window.location.pathname + window.location.search });
}

export async function logout() {
  if (cfg.authMode === 'dev') {
    sessionStorage.removeItem(DEV_KEY);
    window.location.href = '/';
    return;
  }
  await mgr?.signoutRedirect();
}
