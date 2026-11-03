// W-5.10 (Δ) Справочники модели ТО v3.8: версии, происхождение записей, статус верификации (V-DIC-052: candidate не выгружается в XSD)
import { Button, Drawer, Input, Segmented, Space, Table, Tag } from 'antd';
import { observer } from 'mobx-react-lite';
import { useState } from 'react';
import { get, post } from '../api';
import { useLoad } from '../hooks';
import { app } from '../store';
import { Rule, ScreenTitle, fmtDateTime, showError } from '../ui';

const Dict38 = observer(() => {
  const list = useLoad(() => get('/dict38'), []);
  const [dict, setDict] = useState('Steel_Grades');
  const [status, setStatus] = useState('all');
  const [q, setQ] = useState('');
  const [page, setPage] = useState(1);
  const [cur, setCur] = useState<any>(null);
  const entries = useLoad(() => get(`/dict38/${dict}`, { status: status === 'all' ? '' : status, q, page, size: 50 }), [dict, status, q, page]);
  return (
    <div>
      <ScreenTitle code="W-5.10" title={<>Справочники модели ТО v3.8: версии и верификация</>} sub={<>Записи со статусом candidate не выгружаются в XSD<Rule code="V-DIC-052" />. Происхождение записи — source_system, source_code, quality_flags.</>} />
      <div className="split" style={{ gridTemplateColumns: 'minmax(280px, 4fr) 8fr' }}>
        <Table size="small" rowKey="code" loading={list.loading} dataSource={list.data || []} pagination={false}
          onRow={(r: any) => ({ onClick: () => { setDict(r.code); setPage(1); }, className: 'clickable-row', style: r.code === dict ? { background: '#E3EEFB' } : undefined })} columns={[
            { title: 'Справочник', dataIndex: 'code', render: (v, r: any) => <div><b className="mono">{v}</b><div className="hint">{r.group} · версия {r.version}</div></div> },
            { title: 'confirmed', dataIndex: 'confirmed', render: (v) => <span className="mono" style={{ color: '#1E7B34' }}>{v}</span> },
            { title: 'candidate', dataIndex: 'candidate', render: (v) => <span className="mono" style={{ color: v ? '#B54708' : undefined }}>{v}</span> }]} />
        <div>
          <div className="toolbar">
            <Segmented value={status} onChange={(v) => { setStatus(v as string); setPage(1); }} options={[{ value: 'all', label: 'Все' }, { value: 'confirmed', label: 'confirmed' }, { value: 'candidate', label: 'candidate' }]} />
            <Input.Search allowClear placeholder="Код или наименование" style={{ width: 260 }} onSearch={(v) => { setQ(v); setPage(1); }} />
          </div>
          <Table size="small" rowKey="id" loading={entries.loading} dataSource={entries.data?.items || []} scroll={{ x: 900 }}
            pagination={{ current: page, pageSize: 50, total: entries.data?.total || 0, onChange: setPage }} onRow={(r) => ({ onClick: () => setCur(r), className: 'clickable-row' })} columns={[
              { title: 'Код', dataIndex: 'code', render: (v) => <span className="mono">{v}</span> }, { title: 'Наименование', dataIndex: 'name' },
              { title: 'Источник (source_system)', dataIndex: 'sourceSystem' }, { title: 'source_code', dataIndex: 'sourceCode', render: (v) => <span className="mono">{v || '—'}</span> },
              ...(dict === 'Steel_Grades' ? [{ title: 'Нормы HB', render: (_: any, r: any) => <span className="mono">{r.payload.hb_min ?? '—'}–{r.payload.hb_max ?? '—'}</span> },
                { title: 'conflict_state', render: (_: any, r: any) => (r.payload.conflict_state === 'open' ? <Tag color="orange">open (V-DIC-045)</Tag> : r.payload.conflict_state || '—') }] : []),
              { title: 'Флаги качества', dataIndex: 'flags', render: (f: string[]) => f?.map((x) => <Tag key={x} color="orange" className="mono">{x}</Tag>) },
              { title: 'Статус верификации', dataIndex: 'status', render: (s) => <Tag color={s === 'confirmed' ? 'green' : 'orange'} className="mono">{s === 'confirmed' ? 'confirmed' : 'candidate (не попадёт в XSD)'}</Tag> }]} />
        </div>
      </div>
      <Drawer open={!!cur} width={520} onClose={() => setCur(null)} title={cur ? `${dict}: ${cur.code}` : ''} extra={cur && app.can('nsi.edit') && <Button type="primary" onClick={async () => {
        try { await post(`/dict38/entry/${cur.id}/verify`, { status: cur.status === 'confirmed' ? 'candidate' : 'confirmed' }); setCur(null); entries.reload(); list.reload(); } catch (e) { showError(e); }
      }}>{cur.status === 'confirmed' ? 'Вернуть в candidate' : 'Подтвердить (confirmed)'}</Button>}>
        {cur && <Space direction="vertical" style={{ width: '100%' }}>
          <div><b>{cur.name}</b></div>
          <div className="hint">Версия справочника: {(list.data || []).find((x: any) => x.code === dict)?.version} от {fmtDateTime((list.data || []).find((x: any) => x.code === dict)?.publishedAt)}</div>
          <pre className="mono" style={{ background: '#F8FAFC', border: '1px solid #D5DAE1', borderRadius: 6, padding: 10, whiteSpace: 'pre-wrap', fontSize: 12 }}>{JSON.stringify(cur.payload, null, 2)}</pre>
        </Space>}
      </Drawer>
    </div>
  );
});

export default Dict38;
