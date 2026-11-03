// Поля задания на ДО (табл. 79, 81 ТПР): создание и редактирование. Все поля обязательны (R-B301-01), для ВТД шаблон не предусмотрен.
import { AutoComplete, Col, DatePicker, Input, Row, Select } from 'antd';
import dayjs from 'dayjs';
import { observer } from 'mobx-react-lite';
import { useEffect, useState } from 'react';
import { get } from '../api';
import { app } from '../store';
import { Rule } from '../ui';

export interface TaskFormData {
  vid: string; xyz: string; eo_id?: number | null; eo_name: string; deo: string; location: string; brigade: string;
  template_id?: number | null; start_date: string; end_date: string; is_hs?: boolean; version?: number;
}

export const emptyTask = (vid: string): TaskFormData => ({
  vid, xyz: '', eo_id: null, eo_name: '', deo: app.me?.deo || '', location: '', brigade: '',
  template_id: app.refs?.templates.find((t) => t.vid === vid)?.id ?? null, start_date: '', end_date: '',
});

export function validateTask(f: TaskFormData): Record<string, string> {
  const e: Record<string, string> = {};
  (['xyz', 'eo_name', 'deo', 'location', 'brigade', 'start_date', 'end_date'] as const).forEach((k) => { if (!String(f[k] || '').trim()) e[k] = 'Обязательное поле'; });
  if (f.vid !== 'vtd' && !f.template_id) e.template_id = 'Обязательное поле';
  if (f.start_date && f.end_date && f.end_date < f.start_date) e.end_date = 'Дата завершения раньше даты начала';
  return e;
}

const L = ({ children, req = true, rule }: { children: React.ReactNode; req?: boolean; rule?: string }) => (
  <div className="field-label">{children} {req && <span className="req">*</span>}<Rule code={rule} /></div>
);

const TaskForm = observer(({ value, onChange, errors }: { value: TaskFormData; onChange: (v: TaskFormData) => void; errors: Record<string, string> }) => {
  const [eoOpts, setEoOpts] = useState<any[]>([]);
  const set = (p: Partial<TaskFormData>) => onChange({ ...value, ...p });
  const search = async (q: string) => setEoOpts(await get('/refs/eo', { q, vid: value.vid, deo: value.deo }));
  useEffect(() => { search(''); }, [value.vid, value.deo]);
  const tpls = app.refs!.templates.filter((t) => t.vid === value.vid);
  const err = (k: string) => (errors[k] ? <div className="err">{errors[k]}</div> : null);
  const st = (k: string) => (errors[k] ? 'error' : undefined) as any;
  return (
    <Row gutter={[14, 12]}>
      <Col span={24}><L rule="R-B301-01">Вид ДО</L><Input value={app.vidName(value.vid)} readOnly style={{ background: '#F4F6F8' }} /><div className="hint">Заполняется автоматически по фильтру «Вид ДО»</div></Col>
      <Col xs={24} md={12}><L>XYZ</L><Input className="mono" value={value.xyz} status={st('xyz')} placeholder="97488/2/142000094607_X" onChange={(e) => set({ xyz: e.target.value })} />{err('xyz')}</Col>
      <Col xs={24} md={12}><L>Эксплуатирующая организация</L>
        <Select style={{ width: '100%' }} value={value.deo || undefined} status={st('deo')} placeholder="Выберите…" disabled={!!app.me?.deo}
          options={app.refs!.deo.map((d) => ({ value: d.code, label: `${d.code} — ${d.name}` }))} onChange={(v) => set({ deo: v, eo_id: null, eo_name: '' })} />{err('deo')}</Col>
      <Col xs={24} md={12}><L>Объект ДО (единица оборудования)</L>
        <AutoComplete style={{ width: '100%' }} value={value.eo_name} status={st('eo_name')} placeholder="Начните вводить наименование или код ЕО"
          options={eoOpts.map((e) => ({ value: e.name, label: <div><div>{e.name}</div><div className="hint mono">{e.code} · {e.deo} · {e.location}</div></div>, eo: e }))}
          onSearch={search} onChange={(v) => set({ eo_name: v, eo_id: null })}
          onSelect={(_, o: any) => set({ eo_name: o.eo.name, eo_id: o.eo.id, deo: o.eo.deo, location: value.location || o.eo.location })} />{err('eo_name')}</Col>
      <Col xs={24} md={12}><L>Бригада</L>
        <Select style={{ width: '100%' }} value={value.brigade || undefined} status={st('brigade')} placeholder="Выберите…" options={app.refs!.brigades.map((b) => ({ value: b.name, label: b.name }))}
          onChange={(v) => set({ brigade: v })} />{err('brigade')}</Col>
      <Col span={24}><L>Местоположение</L><Input value={value.location} status={st('location')} onChange={(e) => set({ location: e.target.value })} />{err('location')}</Col>
      <Col span={24}><L req={value.vid !== 'vtd'} rule="OQ-04">Шаблон</L>
        {value.vid === 'vtd' ? <div className="banner-warn" style={{ marginBottom: 0 }}>Для ВТД шаблон не предусмотрен (п. 4.4.4 ТПР): технический отчёт загружается в результат ДО файлом.</div>
          : <Select style={{ width: '100%' }} value={value.template_id || undefined} status={st('template_id')} placeholder="Выберите…" options={tpls.map((t) => ({ value: t.id, label: t.name }))}
            onChange={(v) => set({ template_id: v })} />}{err('template_id')}</Col>
      <Col xs={24} md={12}><L>Плановое начало ДО</L>
        <DatePicker style={{ width: '100%' }} format="DD.MM.YYYY" value={value.start_date ? dayjs(value.start_date) : null} status={st('start_date')}
          onChange={(d) => set({ start_date: d ? d.format('YYYY-MM-DD') : '' })} />{err('start_date')}</Col>
      <Col xs={24} md={12}><L rule="OQ-05">Плановое завершение ДО</L>
        <DatePicker style={{ width: '100%' }} format="DD.MM.YYYY" value={value.end_date ? dayjs(value.end_date) : null} status={st('end_date')}
          onChange={(d) => set({ end_date: d ? d.format('YYYY-MM-DD') : '' })} />{err('end_date')}</Col>
    </Row>
  );
});

export default TaskForm;
