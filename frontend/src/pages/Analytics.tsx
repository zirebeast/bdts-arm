// W-4.1 Аналитика (Б320): шаблоны отчётов, параметры, «Отчет о мероприятиях ДТОиР по ЕО», сохранение XLSX/CSV/DOCX, полноэкранный режим
import { DownloadOutlined, FullscreenExitOutlined, FullscreenOutlined, ReloadOutlined, StarFilled, StarOutlined } from '@ant-design/icons';
import { Button, Checkbox, DatePicker, Dropdown, Select, Space, Table } from 'antd';
import dayjs from 'dayjs';
import { observer } from 'mobx-react-lite';
import { useState } from 'react';
import { download, get, post } from '../api';
import { useLoad } from '../hooks';
import { app } from '../store';
import { NoAccess, ScreenTitle, showError } from '../ui';

const WORKS = ['Диагностическое обследование', 'Текущий ремонт', 'Капитальный ремонт', 'Техническое обслуживание'];

const Analytics = observer(() => {
  const [p, setP] = useState<any>({ from: dayjs().subtract(1, 'year').startOf('year').format('YYYY-MM-DD'), to: dayjs().format('YYYY-MM-DD'), deo: '', works: [], tm: [], eo: [] });
  const [rows, setRows] = useState<any[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [panel, setPanel] = useState(true);
  const [fav, setFav] = useState(true);
  const [full, setFull] = useState(false);
  const eos = useLoad(() => get('/refs/eo', { limit: 100 }), []);
  if (!app.can('analytics')) return <NoAccess text="Экранная форма «Аналитика» доступна роли «БДТС. Ответственный ДЭО за контроль технического состояния» (МП-3.5-Б320-14)." />;
  const apply = async () => {
    setBusy(true);
    try { setRows((await post('/analytics/activities', p)).rows); } catch (e) { showError(e); } finally { setBusy(false); }
  };
  return (
    <div style={full ? { position: 'fixed', inset: 0, zIndex: 200, background: '#F4F6F8', padding: 16, overflow: 'auto' } : undefined}>
      <ScreenTitle code="W-4.1" title="Отчет о мероприятиях ДТОиР по ЕО" extra={<>
        <Button onClick={() => setPanel(!panel)}>{panel ? 'Скрыть шаблоны' : 'Показать шаблоны'}</Button>
        <Button icon={<ReloadOutlined />} onClick={apply}>Обновить</Button>
        <Button onClick={() => { setP({ from: '', to: '', deo: '', works: [], tm: [], eo: [] }); setRows(null); }}>Сбросить все фильтры</Button>
        <Dropdown disabled={!rows} menu={{ items: ['xlsx', 'csv', 'docx'].map((f) => ({ key: f, label: f.toUpperCase() })), onClick: (e) => download('/analytics/activities/export', { fmt: e.key }, 'post', p) }}>
          <Button icon={<DownloadOutlined />}>Сохранить</Button></Dropdown>
        <Button icon={full ? <FullscreenExitOutlined /> : <FullscreenOutlined />} onClick={() => setFull(!full)}>{full ? 'Выйти из полноэкранного режима' : 'На весь экран'}</Button>
      </>} />
      <div className="split" style={{ gridTemplateColumns: panel ? 'minmax(220px, 3fr) 9fr' : '1fr' }}>
        {panel && <div className="panel">
          <b>Шаблоны отчётов</b>
          <div className="field-label" style={{ marginTop: 10 }}>Избранное</div>
          {fav ? <div style={{ display: 'flex', justifyContent: 'space-between', background: '#E3EEFB', padding: 6, borderRadius: 4 }}><span>Отчет о мероприятиях ДТОиР</span><StarFilled style={{ color: '#B54708', cursor: 'pointer' }} onClick={() => setFav(false)} /></div> : <span className="hint">Нет шаблонов</span>}
          <div className="field-label" style={{ marginTop: 10 }}>Все шаблоны</div>
          <div style={{ display: 'flex', justifyContent: 'space-between', border: '1px solid #1F5FAD', padding: 6, borderRadius: 4 }}><b>Отчет о мероприятиях ДТОиР</b>{!fav && <StarOutlined style={{ cursor: 'pointer' }} onClick={() => setFav(true)} />}</div>
        </div>}
        <div>
          <div className="panel">
            <Space wrap align="end">
              <div><div className="field-label">Период</div><DatePicker.RangePicker format="DD.MM.YYYY" value={[p.from ? dayjs(p.from) : null, p.to ? dayjs(p.to) : null] as any}
                onChange={(v) => setP({ ...p, from: v?.[0]?.format('YYYY-MM-DD') || '', to: v?.[1]?.format('YYYY-MM-DD') || '' })} /></div>
              {!app.me!.deo && <div><div className="field-label">ДЭО</div><Select style={{ width: 160 }} value={p.deo} onChange={(v) => setP({ ...p, deo: v })} options={[{ value: '', label: 'Все' }, ...app.refs!.deo.map((d) => ({ value: d.code, label: d.code }))]} /></div>}
              <div><div className="field-label">ТМ (множественный выбор)</div><Select mode="multiple" allowClear style={{ width: 300 }} value={p.tm} onChange={(v) => setP({ ...p, tm: v })} options={app.refs!.tms.map((t) => ({ value: t.code, label: `${t.code} · ${t.name}` }))} maxTagCount={1} /></div>
              <div><div className="field-label">ЕО (множественный выбор)</div><Select mode="multiple" allowClear style={{ width: 300 }} value={p.eo} onChange={(v) => setP({ ...p, eo: v })} options={(eos.data || []).map((e: any) => ({ value: e.id, label: `${e.code} · ${e.name}` }))} maxTagCount={1} optionFilterProp="label" /></div>
            </Space>
            <div style={{ marginTop: 10 }}><div className="field-label">Вид работ (множественный выбор)</div><Checkbox.Group value={p.works} options={WORKS} onChange={(v) => setP({ ...p, works: v })} /></div>
            <div style={{ textAlign: 'right' }}><Button type="primary" loading={busy} onClick={apply}>Применить</Button></div>
          </div>
          {rows === null ? <div className="panel" style={{ textAlign: 'center', padding: 40 }}><span className="hint">Задайте параметры отчёта и нажмите «Применить».</span></div> : (
            <Table size="small" bordered rowKey={(_, i) => String(i)} dataSource={rows} pagination={{ pageSize: 50 }} scroll={{ x: 1000 }} columns={[
              { title: <div>№ п/п<div className="mono hint">1</div></div>, width: 60, render: (_: any, __: any, i: number) => i + 1 },
              ...['Краткое описание работ', 'Позиция по схеме', 'Название ЕО', 'Марка или тип оборудования', 'Вид ремонта', 'Дата выполнения', 'Причины невыполнения ремонта'].map((t, k) => ({
                title: <div>{t}<div className="mono hint">{k + 2}</div></div>, dataIndex: k, render: (v: any) => v || '' }))]} />
          )}
        </div>
      </div>
    </div>
  );
});

export default Analytics;
