// Глобальное состояние (MobX): профиль, справочники, уведомления, настройки интерфейса
import { makeAutoObservable, runInAction } from 'mobx';
import { get, post } from './api';

export interface Me {
  username: string; fio: string; position: string; deo: string; display: string;
  roles: { code: string; label: string; short: string; start: string; delta?: boolean }[];
  actions: string[]; editScreens: string[]; startRoute: string; suiaUrl: string; today: string;
}
export interface Refs {
  vids: { key: string; name: string; short: string }[];
  deo: { code: string; name: string }[];
  orgs: { code: string; name: string; kind: string }[];
  brigades: { name: string; members: any[] }[];
  templates: { id: number; no: number; vid: string; name: string }[];
  tms: { code: string; name: string }[];
}

const pref = (k: string, d: string) => { try { return localStorage.getItem(k) ?? d; } catch { return d; } };
const setPref = (k: string, v: string) => { try { localStorage.setItem(k, v); } catch { /* недоступно */ } };

class AppStore {
  me: Me | null = null;
  refs: Refs | null = null;
  unread = 0;
  notes: any[] = [];
  collapsed = pref('bdts.collapsed', '0') === '1';
  techMode = pref('bdts.techMode', '0') === '1';
  /** Последние посещённые разделы (crumbs): по одному на адрес, в порядке посещения. */
  visits: { key: string; path: string; code: string; title: string }[] = [];

  constructor() {
    makeAutoObservable(this);
  }

  async load() {
    const [me, refs] = await Promise.all([get<Me>('/me'), get<Refs>('/refs')]);
    runInAction(() => { this.me = me; this.refs = refs; });
    this.loadNotes();
  }

  async reloadRefs() {
    const refs = await get<Refs>('/refs');
    runInAction(() => { this.refs = refs; });
  }

  /** Все уведомления пользователя; фильтр колокольчика применяется на клиенте и не влияет на другие блоки (кабинет). */
  async loadNotes() {
    try {
      const r = await get('/notifications');
      runInAction(() => { this.notes = r.items; this.unread = r.unread; });
    } catch { /* фоновое обновление */ }
  }

  async markNote(id: number, patch: { read?: boolean; flagged?: boolean }) {
    await post(`/notifications/${id}`, null, patch);
    this.loadNotes();
  }

  async readAll() {
    await post('/notifications-read-all');
    this.loadNotes();
  }

  can(action: string) {
    return !!this.me?.actions.includes(action);
  }

  hasRole(...roles: string[]) {
    return !!this.me?.roles.some((r) => roles.includes(r.code));
  }

  toggleCollapsed() { this.collapsed = !this.collapsed; setPref('bdts.collapsed', this.collapsed ? '1' : '0'); }
  toggleTech() { this.techMode = !this.techMode; setPref('bdts.techMode', this.techMode ? '1' : '0'); }
  visit(v: { key: string; path: string; code: string; title: string }) { this.visits = [...this.visits.filter((x) => x.key !== v.key), v].slice(-3); }

  vidName(key: string) {
    return this.refs?.vids.find((v) => v.key === key)?.name || key;
  }
}

export const app = new AppStore();
