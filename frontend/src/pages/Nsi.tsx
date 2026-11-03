// W-5.1…W-5.9 Справочники НСИ Б304–Б315: реестр + drawer карточки (R-NSI-01 обязательность, R-NSI-02 пометка на удаление)
import { DownloadOutlined, PlusOutlined } from '@ant-design/icons';
import { Button, DatePicker, Drawer, Input, Modal, Select, Space, Table, message } from 'antd';
import dayjs from 'dayjs';
import { observer } from 'mobx-react-lite';
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { del, download, get, post, put } from '../api';
import { useLoad } from '../hooks';
import { app } from '../store';
import { KV, Rule, ScreenTitle, StatusChip, fieldErrors, fmtDate, showError } from '../ui';

const Nsi = observer(() => {
  const { code = 'B306' } = useParams();
  const nav = useNavigate();
  const cats = useLoad(() => get('/nsi'), []);
  const [q, setQ] = useState('');
  const [page, setPage] = useState(1);
  const { data, loading, reload } = useLoad(() => get(`/nsi/${code}`, { q, page, size: 50 }), [code, q, page]);
  const [cur, setCur] = useState<any>(null);
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const can = app.can('nsi.edit');
  const schema = data?.schema;
  const screen = (cats.data || []).find((c: any) => c.code === code)?.screen || 'W-5.1';
  const fmt = (f: any, v: any) => (f.type === 'date' ? fmtDate(v) : v || '—');
  const cols: any[] = schema ? [
    { title: 'ID записи', dataIndex: 'recordNo', width: 90, render: (v: number) => <span className="mono">{v}</span> },
    ...schema.fields.map((f: any) => ({ title: f.label, key: f.key, render: (_: any, r: any) => fmt(f, r.data[f.key]) })),
    { title: 'Дата создания записи', dataIndex: 'createdAt', render: fmtDate }, { title: 'Дата последнего обновления', dataIndex: 'updatedAt', render: fmtDate },
    { title: 'Статус записи', dataIndex: 'recordStatus', render: (s: string) => <StatusChip status={s} compact /> },
    ...(schema.notes ? [{ title: 'Примечания', dataIndex: 'notes' }] : []),
  ] : [];
  const save = async () => {
    setBusy(true);
    try {
      if (cur.id) await put(`/nsi/${code}/${cur.id}`, { data: cur.data, notes: cur.notes }); else await post(`/nsi/${code}`, { data: cur.data, notes: cur.notes });
      message.success('Запись справочника сохранена');
      setCur(null);
      reload();
    } catch (e) { setErrs(fieldErrors(e)); showError(e); } finally { setBusy(false); }
  };
  return (
    <div>
      <ScreenTitle code={screen} title={<>Справочник «{schema?.title || '…'}» <span className="hint mono">{app.techMode ? `(${code.replace('B', 'Б')})` : ''}</span></>} extra={<>
        <Button icon={<DownloadOutlined />} onClick={() => download(`/nsi/${code}/export.xlsx`)}>Сохранить в Excel</Button>
        {can && <Button type="primary" icon={<PlusOutlined />} onClick={() => { setErrs({}); setCur({ data: {}, notes: '', recordStatus: 'Действует' }); }}>Создать запись</Button>}
      </>} />
      <div className="toolbar">
        <Space wrap><span className="field-label" style={{ margin: 0 }}>Справочник</span>
          <Select style={{ width: 320 }} value={code} onChange={(v) => { nav(`/nsi/${v}`); setPage(1); }} options={(cats.data || []).map((c: any) => ({ value: c.code, label: `${c.title} (${c.count})` }))} /></Space>
        <Input.Search allowClear placeholder="Поиск по значениям" style={{ width: 280 }} onSearch={setQ} />
      </div>
      <Table size="small" rowKey="id" loading={loading} columns={cols} dataSource={data?.items || []} scroll={{ x: 1100 }}
        pagination={{ current: page, pageSize: 50, total: data?.total || 0, onChange: setPage }} onRow={(r) => ({ onClick: () => { setErrs({}); setCur(JSON.parse(JSON.stringify(r))); }, className: 'clickable-row' })} />
      <Drawer open={!!cur} width={480} onClose={() => setCur(null)} title={`${cur?.id ? 'Карточка записи' : 'Новая запись'}: ${schema?.title || ''}`} destroyOnClose
        footer={<div style={{ display: 'flex', justifyContent: 'space-between' }}>
          {cur?.id && can && cur.recordStatus !== 'Помечено на удаление' ? <Button danger onClick={() => Modal.confirm({ title: 'Пометить запись на удаление?', content: 'Запись получит статус «Помечено на удаление» и не будет предлагаться для выбора.', okText: 'Пометить', cancelText: 'Отмена',
            onOk: async () => { await del(`/nsi/${code}/${cur.id}`); message.warning('Запись помечена на удаление'); setCur(null); reload(); } })}>Пометить на удаление<Rule code="R-NSI-02" /></Button> : <span />}
          <Space><Button onClick={() => setCur(null)}>{can ? 'Отмена' : 'Закрыть'}</Button>{can && <Button type="primary" loading={busy} onClick={save}>Сохранить</Button>}</Space></div>}>
        {cur && schema && <Space direction="vertical" style={{ width: '100%' }}>
          {cur.id && <div><div className="field-label">ID записи</div><Input disabled value={cur.recordNo} /></div>}
          {schema.fields.map((f: any) => {
            const v = cur.data[f.key] ?? '';
            const set = (x: any) => setCur({ ...cur, data: { ...cur.data, [f.key]: x } });
            return <div key={f.key}>
              <div className="field-label">{f.label} {f.req && !f.auto && <span className="req">*</span>}{f.ref && <span className="hint"> (ссылка {f.ref.replace('B', 'Б')})</span>}</div>
              {f.auto ? <Input disabled value={v || 'Заполняется автоматически'} />
                : f.type === 'date' ? <DatePicker style={{ width: '100%' }} format="DD.MM.YYYY" disabled={!can} value={v ? dayjs(v) : null} onChange={(d) => set(d ? d.format('YYYY-MM-DD') : '')} status={errs[f.key] ? 'error' : undefined} />
                  : f.type === 'select' ? <Select style={{ width: '100%' }} disabled={!can} value={v || undefined} onChange={set} options={(schema.options[f.key] || []).map((o: string) => ({ value: o, label: o }))} status={errs[f.key] ? 'error' : undefined} />
                    : <Input disabled={!can} value={v} onChange={(e) => set(e.target.value)} status={errs[f.key] ? 'error' : undefined} className={f.type === 'num' ? 'mono' : ''} />}
              {errs[f.key] && <div className="err">{errs[f.key]}</div>}
            </div>;
          })}
          <div style={{ borderTop: '1px solid #D5DAE1', paddingTop: 10 }}>
            <div className="field-label" style={{ textTransform: 'uppercase' }}>Системные поля</div>
            <KV cols={1} items={[['Дата создания записи', fmtDate(cur.createdAt)], ['Дата последнего обновления записи', fmtDate(cur.updatedAt)], ['Статус записи', <StatusChip status={cur.recordStatus} compact />]]} />
            {schema.notes && <><div className="field-label" style={{ marginTop: 8 }}>Примечания</div><Input disabled={!can} value={cur.notes} onChange={(e) => setCur({ ...cur, notes: e.target.value })} /></>}
          </div>
          <Rule code="R-NSI-01" />
        </Space>}
      </Drawer>
    </div>
  );
});

export default Nsi;
