// W-3.7 (Δ) Подготовка к планированию: отбор ЕО по признакам, раздельные метки (D-PLN-02), выгрузка перечня и история выгрузок (D-PLN-01)
import { DownloadOutlined, HistoryOutlined, SyncOutlined } from '@ant-design/icons';
import { Button, Drawer, Input, Space, Table, Tag, Tooltip, message } from 'antd';
import { observer } from 'mobx-react-lite';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { download, get, post } from '../api';
import { useLoad } from '../hooks';
import { app } from '../store';
import { Rule, ScreenTitle, fmtDate, fmtDateTime, showError } from '../ui';

const Planning = observer(() => {
  const [chips, setChips] = useState<string[]>(['Дефекты прошлого периода', 'Истекает срок ЭПБ']);
  const [q, setQ] = useState('');
  const [sel, setSel] = useState<number[]>([]);
  const [hist, setHist] = useState(false);
  const { data, loading, reload } = useLoad(() => get('/planning', { criteria: chips.join('|'), q }), [chips, q]);
  const exports = useLoad(() => get('/planning/exports'), [hist]);
  const can = app.can('plan');
  const mark = async (m: string) => {
    try { await post('/planning/marks', { eoIds: sel, mark: m, value: true }); message.success(`Выбранным ЕО установлена метка «${m === 'mark3y' ? '3-летний план' : 'Следующий год'}»`); reload(); } catch (e) { showError(e); }
  };
  return (
    <div>
      <ScreenTitle code="W-3.7" title={<>Подготовка к планированию: отбор объектов по признакам</>} sub="Раздельная установка меток «3-летний план» и «Следующий год» и история выгрузок перечней"
        extra={<>{can && <Button icon={<SyncOutlined />} onClick={async () => { const r = await post('/planning/sync-bdo'); message.info(r.note || 'Синхронизация с МП-3 «БДО» выполнена'); reload(); }}>Обновить МП-3</Button>}
          <Button icon={<HistoryOutlined />} onClick={() => setHist(true)}>История выгрузок</Button></>} />
      <div className="panel">
        <Space wrap>
          {(data?.criteria || []).map((c: string) => {
            const dis = c === 'Нет паспорта';
            const on = chips.includes(c);
            return <Tooltip key={c} title={dis ? 'Признак «нет паспорта»: источник признака уточняется (OQ-24), используется флаг БДО' : undefined}>
              <Tag.CheckableTag checked={on} onChange={(v) => setChips(v ? [...chips, c] : chips.filter((x) => x !== c))} style={{ border: '1px solid #D5DAE1', padding: '2px 10px', borderRadius: 12 }}>{c}</Tag.CheckableTag></Tooltip>;
          })}
          <Input.Search allowClear placeholder="Код или наименование ЕО" style={{ width: 260 }} onSearch={setQ} />
        </Space>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 10, gap: 8, flexWrap: 'wrap', borderTop: '1px solid #EEF1F4', paddingTop: 10 }}>
          <Space wrap>{can && <>
            <Button disabled={!sel.length} style={{ color: '#1565C0', background: '#E3EEFB', borderColor: '#B6D4F7' }} onClick={() => mark('mark3y')}>+ Метка «3-летний план»</Button>
            <Button disabled={!sel.length} style={{ color: '#1E7B34', background: '#E5F4E8', borderColor: '#B7E1C0' }} onClick={() => mark('markNextYear')}>+ Метка «Следующий год»</Button>
            <Rule code="D-PLN-02" /></>}
            <span className="hint">Выбрано: {sel.length} из {data?.items?.length || 0}. Признаки объединяются по ИЛИ.</span>
          </Space>
          {can && <Button type="primary" disabled={!sel.length} onClick={async () => {
            try { const r = await post('/planning/export', { eoIds: sel, criteria: chips }); message.success(`Перечень ${r.number} отправлен Роли 1 и записан в историю выгрузок`); download(`/planning/exports/${r.id}.xlsx`); exports.reload(); } catch (e) { showError(e); }
          }}>Выгрузить и отправить перечень Роли 1</Button>}
        </div>
      </div>
      <Table size="small" rowKey="id" loading={loading} dataSource={data?.items || []} pagination={{ pageSize: 25 }} scroll={{ x: 1200 }}
        rowSelection={{ selectedRowKeys: sel, onChange: (k) => setSel(k as number[]) }} columns={[
          { title: 'Код и наименование ЕО', render: (_: any, r: any) => <Link to={`/eo/${r.id}`}><span className="mono">{r.code}</span> · {r.name}</Link> },
          { title: 'Техническое место', dataIndex: 'tm', render: (v) => <span className="mono hint">{v}</span> }, { title: 'ДЭО', dataIndex: 'deo' }, { title: 'Класс', dataIndex: 'class' },
          { title: 'Дефекты', dataIndex: 'defects', render: (d: string[]) => (d.length ? d.map((x) => <div key={x}>{x}</div>) : 'Нет') },
          { title: 'Срок ЭПБ / след. ТД', dataIndex: 'epbDate', render: fmtDate }, { title: 'Последнее ДО', dataIndex: 'lastDo', render: fmtDate },
          { title: 'Признаки', dataIndex: 'matched', render: (m: string[]) => m.map((x) => <Tag key={x}>{x}</Tag>) },
          { title: 'Метка «3-летний план»', dataIndex: 'mark3y', render: (v) => (v ? <Tag color="blue">3-летний план</Tag> : '—') },
          { title: 'Метка «Следующий год»', dataIndex: 'markNextYear', render: (v) => (v ? <Tag color="green">Следующий год</Tag> : '—') }]} />
      <Drawer open={hist} onClose={() => setHist(false)} width={480} title={<>История выгрузок перечней <Rule code="D-PLN-01" /></>}>
        {(exports.data || []).map((h: any) => (
          <div key={h.id} className="panel" style={{ background: '#F8FAFC' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}><b className="mono" style={{ color: '#1F5FAD' }}>{h.number}</b><span className="mono">{fmtDateTime(h.date)}</span></div>
            <div>Выгружено объектов: <b>{h.count} ЕО</b> · Метка: <b>{h.mark}</b></div>
            <div className="hint">{h.user} → {h.recipient}</div>
            <a onClick={() => download(`/planning/exports/${h.id}.xlsx`)}><DownloadOutlined /> Скачать перечень</a>
          </div>
        ))}
      </Drawer>
    </div>
  );
});

export default Planning;
