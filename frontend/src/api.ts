// HTTP-клиент: JWT в Authorization, глобальная обработка ошибок (401 → вход, 4xx/5xx → уведомление с кодом правила)
import { message } from 'antd';
import axios, { AxiosError } from 'axios';
import { getToken, relogin } from './auth';

export const http = axios.create({ baseURL: '/api/v1', timeout: 60000 });

http.interceptors.request.use((c) => {
  const t = getToken();
  if (t) c.headers.Authorization = `Bearer ${t}`;
  return c;
});

export interface ApiError {
  status: number;
  detail: string;
  rule?: string;
  fields?: Record<string, any>;
}

http.interceptors.response.use(
  (r) => r,
  async (e: AxiosError<any>) => {
    const status = e.response?.status || 0;
    let data: any = e.response?.data;
    if (data instanceof Blob) {
      try { data = JSON.parse(await data.text()); } catch { data = {}; }
    }
    const err: ApiError = {
      status,
      detail: (typeof data?.detail === 'string' ? data.detail : Array.isArray(data?.detail) ? data.detail.map((d: any) => d.msg).join('; ') : '') || (status ? `Ошибка ${status}` : 'Нет связи с сервисом БДТС'),
      rule: data?.rule,
      fields: data?.fields,
    };
    if (status === 401) {
      message.warning('Сессия истекла — выполняется повторный вход');
      await relogin();
    } else if (status === 409) {
      message.warning(err.detail);
    } else if (status >= 500 || status === 0) {
      message.error(`${err.detail} (HTTP ${status || '—'})`);
    }
    return Promise.reject(err);
  },
);

export async function get<T = any>(url: string, params?: any): Promise<T> {
  return (await http.get(url, { params })).data;
}
export async function post<T = any>(url: string, body?: any, params?: any): Promise<T> {
  return (await http.post(url, body, { params })).data;
}
export async function put<T = any>(url: string, body?: any): Promise<T> {
  return (await http.put(url, body)).data;
}
export async function patch<T = any>(url: string, body?: any): Promise<T> {
  return (await http.patch(url, body)).data;
}
export async function del<T = any>(url: string): Promise<T> {
  return (await http.delete(url)).data;
}

export async function upload<T = any>(url: string, files: Record<string, File | File[]>, fields: Record<string, string> = {}): Promise<T> {
  const fd = new FormData();
  Object.entries(files).forEach(([k, v]) => (Array.isArray(v) ? v : [v]).forEach((f) => fd.append(k, f)));
  Object.entries(fields).forEach(([k, v]) => fd.append(k, v));
  return (await http.post(url, fd)).data;
}

export async function uploadFile(file: File, entityType = 'draft', entityId = '', kind = 'attachment') {
  return upload<{ id: number; name: string; size: number }>('/files', { file }, { entity_type: entityType, entity_id: entityId, kind });
}

/** Скачать файл с сервера (с авторизацией) и сохранить под именем из Content-Disposition. */
export async function download(url: string, params?: any, method: 'get' | 'post' = 'get', body?: any) {
  const r = method === 'get' ? await http.get(url, { params, responseType: 'blob' }) : await http.post(url, body, { params, responseType: 'blob' });
  const cd = r.headers['content-disposition'] || '';
  const m = /filename\*=UTF-8''([^;]+)/.exec(cd);
  const name = m ? decodeURIComponent(m[1]) : 'file';
  const a = document.createElement('a');
  a.href = URL.createObjectURL(r.data);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 10000);
  return name;
}

export function errText(e: any): string {
  return e?.detail || String(e);
}
