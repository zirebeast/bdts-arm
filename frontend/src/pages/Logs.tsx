// W-3.6 «Лог» (т.113) и «Лог загрузки данных» (т.114)
import { ReloadOutlined } from '@ant-design/icons';
import { Button, Select, Table, Tabs, Tag } from 'antd';
import { observer } from 'mobx-react-lite';
import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { download, get } from '../api';
import { useLoad } from '../hooks';
import { ScreenTitle, StatusChip, fmtDateTime } from '../ui';

const Logs = observer(() => {
  const [sp] = useSearchParams();
  const [tab, setTab] = useState(sp.get('log') ? 'entries' : 'log');
  const [logId, setLogId] = useState<number | undefined>(sp.get('log') ? Number(sp.get('log')) : undefined);
  const [level, setLevel] = useState('');
  const logs = useLoad(() => get('/logs', { size: 100 }), []);
  const entries = useLoad(() => get('/logs/entries', { log_id: logId, level, size: 300 }), [logId, level]);
  const ST: Record<string, string> = { done: 'Завершено', error: 'Ошибка', queued: 'Не начато', running: 'В работе' };
  return (
    <div>
      <ScreenTitle code="W-3.6" title="Лог и лог загрузки данных" extra={<Button icon={<ReloadOutlined />} onClick={() => { logs.reload(); entries.reload(); }}>Обновить</Button>} />
      <div className="panel">
        <Tabs activeKey={tab} onChange={setTab} items={[
          { key: 'log', label: 'Лог', children: <Table size="small" rowKey="id" loading={logs.loading} dataSource={logs.data?.items || []} pagination={{ pageSize: 20 }}
            onRow={(r: any) => ({ onClick: () => { setLogId(r.id); setTab('entries'); }, className: 'clickable-row' })} columns={[
              { title: 'id лога', dataIndex: 'id', render: (v) => <span className="mono">{v}</span> }, { title: 'Дата', dataIndex: 'date', render: fmtDateTime }, { title: 'Наименование', dataIndex: 'name' },
              { title: 'Имя файла', dataIndex: 'file', render: (v, r: any) => (r.fileId ? <a className="mono" onClick={(e) => { e.stopPropagation(); download(`/files/${r.fileId}`); }}>{v}</a> : <span className="mono">{v}</span>) },
              { title: 'Описание', dataIndex: 'description' }, { title: 'Состояние', dataIndex: 'state', render: (s) => <StatusChip status={ST[s] || s} compact /> }, { title: 'Автор', dataIndex: 'author' }]} /> },
          { key: 'entries', label: 'Логи загрузки данных', children: <>
            <div style={{ display: 'flex', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
              <Select style={{ width: 320 }} allowClear placeholder="Все операции" value={logId} onChange={setLogId}
                options={(logs.data?.items || []).map((l: any) => ({ value: l.id, label: `${l.id} · ${l.name} · ${l.file}` }))} />
              <Select style={{ width: 200 }} value={level} onChange={setLevel} options={[{ value: '', label: 'Все типы' }, ...['Информация', 'Предупреждение', 'Ошибка'].map((x) => ({ value: x, label: x }))]} />
            </div>
            <Table size="small" rowKey="id" loading={entries.loading} dataSource={entries.data?.items || []} pagination={{ pageSize: 30 }}
              rowClassName={(r: any) => (r.level === 'Предупреждение' ? 'row-warn' : '')} columns={[
                { title: 'Дата', dataIndex: 'date', render: fmtDateTime }, { title: 'Наименование', dataIndex: 'name' },
                { title: 'Тип', dataIndex: 'level', render: (l) => <Tag color={l === 'Предупреждение' ? 'orange' : l === 'Ошибка' ? 'red' : 'blue'}>{l}</Tag> },
                { title: 'Имя файла', dataIndex: 'file', render: (v) => <span className="mono">{v}</span> }, { title: 'Описание', dataIndex: 'text' }, { title: 'id строки', dataIndex: 'row', render: (v) => <span className="mono">{v || '—'}</span> }]} />
          </> },
        ]} />
      </div>
    </div>
  );
});

export default Logs;
