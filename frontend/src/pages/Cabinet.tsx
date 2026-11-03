// W-0.4 (Δ) Личный кабинет участника: объединённые виджеты по всем ролям пользователя (без переключения ролей)
import { Badge, Card, Select, Space } from 'antd';
import { observer } from 'mobx-react-lite';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { get } from '../api';
import LoadState from '../components/LoadState';
import { useLoad } from '../hooks';
import { app } from '../store';
import { ScreenTitle, StatusChip } from '../ui';

const Cabinet = observer(() => {
  const nav = useNavigate();
  const [deo, setDeo] = useState('');
  const { data, loading, error, reload } = useLoad(() => get('/cabinet', { deo }), [deo]);
  const notes = app.notes.filter((n: any) => !deo || !n.deo || n.deo === deo).slice(0, 6);
  return (
    <div>
      <ScreenTitle code="W-0.4" title={<>Личный кабинет</>} sub="Сводная панель задач, входящих перечней, запросов на расхождения и технических отчётов по вашим ролям"
        extra={!app.me?.deo && <Space><span className="hint">ДЭО</span><Select style={{ width: 200 }} value={deo} onChange={setDeo} options={[{ value: '', label: 'Все ДЭО' }, ...app.refs!.deo.map((d) => ({ value: d.code, label: d.code }))]} /></Space>} />
      <LoadState loading={loading} error={error} reload={reload}>{() => (
        <>
          <div className="grid g4" style={{ marginBottom: 12 }}>
            {data.widgets.map((w: any) => (
              <button key={w.title} className="kpi" onClick={() => nav(w.link)}>
                <div className="hint">{w.title}</div>
                <div className="v">{w.count}</div>
                <StatusChip status={w.badge} compact />
              </button>
            ))}
          </div>
          <div className="grid g2">
            <Card size="small" title="Последние уведомления">
              {notes.length ? notes.map((n) => <div key={n.id} style={{ padding: '6px 0', borderBottom: '1px solid #EEF1F4' }}><a onClick={() => { app.markNote(n.id, { read: true }); if (n.link) nav(n.link); }} style={{ fontWeight: n.read ? 400 : 600, color: '#1B1F24' }}>{n.title}</a>{!n.read && <Badge status="processing" style={{ marginLeft: 6 }} />}<div className="hint">{n.detail}</div></div>) : <span className="hint">Уведомлений нет</span>}
            </Card>
            <Card size="small" title="Мои роли и доступ">
              {app.me!.roles.map((r) => <div key={r.code} style={{ marginBottom: 6 }}><b>{r.label}</b> <span className="hint mono">{r.code}</span></div>)}
              <div className="hint" style={{ marginTop: 8 }}>{app.me!.deo ? `Данные ограничены по ДЭО: ${app.me!.deo}` : deo ? `Доступ ко всем ДЭО · показаны данные ${deo}` : 'Доступ ко всем ДЭО'}</div>
            </Card>
          </div>
        </>
      )}</LoadState>
    </div>
  );
});

export default Cabinet;
