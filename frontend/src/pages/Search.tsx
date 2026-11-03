// W-0.2 Поиск объектов (R-SRCH-01: «*», «?», «\») + W-0.3 конструктор фильтров + Δ личные шаблоны поиска и история запросов (D-SRCH-01)
import { DeleteOutlined, FilterOutlined, SaveOutlined, SearchOutlined, SettingOutlined } from '@ant-design/icons';
import { Button, Checkbox, DatePicker, Dropdown, Input, Modal, Popover, Select, Space, Switch, Table, Tag, message } from 'antd';
import dayjs from 'dayjs';
import { observer } from 'mobx-react-lite';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { del, get, post } from '../api';
import { app } from '../store';
import { Rule, ScreenTitle, fmtDate, showError } from '../ui';

const ALL_COLS = ['Название', 'ID', 'Класс', 'Описание', 'ДЭО', 'Дата создания', 'Автор', 'Автор изменения', 'Дата изменения'];
const HIST_KEY = 'bdts.searchHistory';
interface Filters { classes: string[]; deo: string; from: string; to: string }

const Search = observer(() => {
  const nav = useNavigate();
  const [q, setQ] = useState('Подогреватель*');
  const [exact, setExact] = useState(false);
  const [att, setAtt] = useState(true);
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [hidden, setHidden] = useState<string[]>([]);
  const [filters, setFilters] = useState<Filters>({ classes: ['eo', 'tm', 'ts'], deo: '', from: '', to: '' });
  const [fOpen, setFOpen] = useState(false);
  const [draft, setDraft] = useState<Filters>(filters);
  const [saved, setSaved] = useState<any[]>([]);
  const [history, setHistory] = useState<string[]>(() => { try { return JSON.parse(localStorage.getItem(HIST_KEY) || '[]'); } catch { return []; } });

  const run = async (query = q, f = filters) => {
    if (query.length > 1000) { message.error('Строка поиска — не более 1000 символов'); return; }
    setLoading(true);
    try {
      const r = await get('/search', { q: query, classes: f.classes.join(','), deo: f.deo, date_from: f.from, date_to: f.to, exact, attachments: att });
      setRows(r.items);
      const h = [query, ...history.filter((x) => x !== query)].slice(0, 10);
      setHistory(h);
      try { localStorage.setItem(HIST_KEY, JSON.stringify(h)); } catch { /* недоступно */ }
    } catch (e) { showError(e); } finally { setLoading(false); }
  };
  const loadSaved = () => get('/saved-searches').then(setSaved);
  useEffect(() => { run(); loadSaved(); }, []);
  useEffect(() => { run(); }, [att, exact]);

  const val = (r: any, c: string) => ({ 'Название': r.name, ID: r.code, 'Класс': r.cls, 'Описание': r.desc, 'ДЭО': r.deo, 'Дата создания': fmtDate(r.created), 'Автор': r.author, 'Автор изменения': r.modAuthor, 'Дата изменения': fmtDate(r.mod) } as any)[c];
  const cols: any[] = ALL_COLS.filter((c) => !hidden.includes(c)).map((c) => ({
    title: c, key: c, render: (_: any, r: any) => (c === 'Название' ? <a onClick={() => nav(r.link)}>{r.name}</a> : <span className={c === 'ID' ? 'mono' : ''}>{val(r, c)}</span>),
    sorter: (a: any, b: any) => String(val(a, c)).localeCompare(String(val(b, c)), 'ru'),
  }));
  const conds = filters.classes.length + (filters.deo ? 1 : 0) + (filters.from || filters.to ? 1 : 0);
  return (
    <div>
      <ScreenTitle code="W-0.2" title="Поиск объектов" />
      <div className="panel">
        <Space.Compact style={{ width: '100%' }}>
          <Input size="large" prefix={<SearchOutlined />} maxLength={1000} value={q} onChange={(e) => setQ(e.target.value)} onPressEnter={() => run()}
            placeholder="Название объекта или ID (подстановки *, ?, экранирование \)" suffix={<Popover trigger="click" title="Настройка поиска" content={
              <Space><Switch size="small" checked={exact} onChange={setExact} /> Только точные совпадения</Space>}><SettingOutlined style={{ cursor: 'pointer' }} /></Popover>} />
          <Button size="large" type="primary" onClick={() => run()}>Найти</Button>
        </Space.Compact>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 10, flexWrap: 'wrap', gap: 8 }}>
          <Space wrap>
            <Button icon={<FilterOutlined />} type="primary" ghost onClick={() => { setDraft(filters); setFOpen(true); }}>Фильтры ({conds})</Button>
            <Checkbox checked={att} onChange={(e) => setAtt(e.target.checked)}>Показать вложения (записи о ТС)</Checkbox>
            <Rule code="R-SRCH-01" />
            <Select style={{ width: 260 }} placeholder="Мои шаблоны поиска…" value={null as any} options={saved.map((s) => ({ value: s.id, label: s.name }))}
              onChange={(id) => { const s = saved.find((x) => x.id === id); if (s) { setQ(s.query); const f = s.filters?.[0] || filters; setFilters(f); run(s.query, f); } }}
              dropdownRender={(menu) => <>{menu}{saved.length > 0 && <div style={{ padding: 6, borderTop: '1px solid #EEF1F4' }}>{saved.map((s) => <Tag key={s.id} closable onClose={async () => { await del(`/saved-searches/${s.id}`); loadSaved(); }}>{s.name}</Tag>)}</div>}</>} />
            <Button icon={<SaveOutlined />} onClick={() => { let name = q; Modal.confirm({ title: 'Сохранить шаблон поиска', content: <Input defaultValue={q} onChange={(e) => { name = e.target.value; }} />,
              okText: 'Сохранить', cancelText: 'Отмена', onOk: async () => { await post('/saved-searches', { name, query: q, filters: [filters] }); loadSaved(); message.success('Шаблон поиска сохранён'); } }); }}>Сохранить шаблон</Button>
            <Dropdown menu={{ items: history.map((h) => ({ key: h, label: h })), onClick: (e) => { setQ(e.key); run(e.key); } }} disabled={!history.length}><Button>История запросов</Button></Dropdown>
          </Space>
          <Popover trigger="click" title="Настройка столбцов" content={<Space direction="vertical">{ALL_COLS.map((c) => <Checkbox key={c} disabled={c === 'Название'} checked={!hidden.includes(c)}
            onChange={(e) => setHidden(e.target.checked ? hidden.filter((x) => x !== c) : [...hidden, c])}>{c}</Checkbox>)}</Space>}><Button>Настроить столбцы</Button></Popover>
        </div>
      </div>
      <Table size="small" rowKey={(r) => `${r.kind}-${r.id}`} loading={loading} columns={cols} dataSource={rows} pagination={{ pageSize: 20 }} scroll={{ x: 1100 }}
        locale={{ emptyText: 'По заданным условиям записей не найдено. Измените параметры фильтрации или сбросьте фильтры.' }} />
      <Modal open={fOpen} title={<>Фильтры <span className="hint">(W-0.3)</span></>} width={640} onCancel={() => setFOpen(false)} footer={<>
        <Button danger icon={<DeleteOutlined />} onClick={() => setDraft({ classes: ['eo', 'tm', 'ts'], deo: '', from: '', to: '' })}>Удалить все условия</Button>
        <Button onClick={() => setFOpen(false)}>Отмена</Button>
        <Button type="primary" onClick={() => { setFilters(draft); setFOpen(false); run(q, draft); message.success('Фильтры применены'); }}>Применить</Button></>}>
        <p className="hint">Значения внутри одного условия связаны логическим ИЛИ, условия между собой — логическим И.</p>
        <div className="field-label">Класс</div>
        <Checkbox.Group value={draft.classes} onChange={(v) => setDraft({ ...draft, classes: v as string[] })} options={[{ value: 'eo', label: 'Единица оборудования (МП-3)' }, { value: 'tm', label: 'Техническое место (МП-3)' }, { value: 'ts', label: 'Запись о техническом состоянии' }]} />
        <div className="field-label" style={{ marginTop: 12 }}>Свойство: ДЭО</div>
        <Select style={{ width: 300 }} allowClear value={draft.deo || undefined} placeholder="Любая" onChange={(v) => setDraft({ ...draft, deo: v || '' })} options={app.refs!.deo.map((d) => ({ value: d.code, label: d.code }))} />
        <div className="field-label" style={{ marginTop: 12 }}>Дата изменения (диапазон)</div>
        <DatePicker.RangePicker format="DD.MM.YYYY" value={draft.from || draft.to ? [draft.from ? dayjs(draft.from) : null, draft.to ? dayjs(draft.to) : null] as any : null}
          onChange={(v) => setDraft({ ...draft, from: v?.[0]?.format('YYYY-MM-DD') || '', to: v?.[1]?.format('YYYY-MM-DD') || '' })} />
      </Modal>
    </div>
  );
});

export default Search;
