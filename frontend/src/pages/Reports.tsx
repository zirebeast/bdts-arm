// W-2.3 (Δ) Реестр технических отчётов: ИУС ГД (XML v3.8) и хозспособ; версии (D-TO-01), несопоставленные ЕО (D-TO-05)
import { EditOutlined, UploadOutlined, WarningOutlined } from '@ant-design/icons';
import { Button, Input, Select, Table, Tag } from 'antd';
import { observer } from 'mobx-react-lite';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { get } from '../api';
import UploadWizard from '../components/UploadWizard';
import { useLoad } from '../hooks';
import { app } from '../store';
import { Rule, ScreenTitle, StatusChip, fmtDate } from '../ui';

const Reports = observer(() => {
  const nav = useNavigate();
  const [f, setF] = useState({ source: '', profile: '', status: '', q: '' });
  const [page, setPage] = useState(1);
  const [wizard, setWizard] = useState(false);
  const { data, loading } = useLoad(() => get('/reports', { ...f, page, size: 20 }), [f, page]);
  const cols: any[] = [
    { title: '№ и дата ТО', dataIndex: 'number', render: (v: string, r: any) => <div><b className="mono" style={{ color: '#1F5FAD' }}>{v}</b><div className="hint">от {fmtDate(r.date)} · {r.title}</div></div> },
    { title: 'Профиль XSD', dataIndex: 'profileName', render: (v: string) => <span className="mono">{v}</span> },
    { title: 'Исполнитель', dataIndex: 'executor' }, { title: 'ДЭО', dataIndex: 'deo' },
    { title: 'Кол-во ЕО', render: (_: any, r: any) => <span><b>{r.eoCount} ЕО</b>{r.unmappedCount > 0 && <Tag color="orange" icon={<WarningOutlined />} style={{ marginLeft: 6 }}>{r.unmappedCount} не сопост.</Tag>}</span> },
    { title: 'Строка ПП / Заказ', dataIndex: 'ppLine' }, { title: 'Источник', dataIndex: 'source' },
    { title: 'Статус ТО', dataIndex: 'status', render: (s: string) => <StatusChip status={s} compact /> },
    { title: 'Версия', dataIndex: 'version', render: (v: string) => <Tag className="mono">{v}</Tag> },
  ];
  return (
    <div>
      <ScreenTitle code="W-2.3" title={<>Реестр технических отчётов</>} extra={<>
        {app.can('to.hs') && <Button icon={<EditOutlined />} onClick={() => nav('/hs')}>Результаты ДО хозспособом</Button>}
        {app.can('to.upload') && <Button type="primary" icon={<UploadOutlined />} onClick={() => setWizard(true)}>Загрузить ТО (XML v3.8)</Button>}
      </>} />
      <div className="toolbar">
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Select style={{ width: 260 }} value={f.source} onChange={(v) => setF({ ...f, source: v })} options={[{ value: '', label: 'Все источники (ИУС ГД + Хозспособ)' }, { value: 'gd', label: 'ИУС ГД' }, { value: 'hs', label: 'Хозспособ ДЭО' }]} />
          <Select style={{ width: 230 }} value={f.profile} onChange={(v) => setF({ ...f, profile: v })} options={[{ value: '', label: 'Все профили' }, ...['to_grs', 'to_tpa', 'to_vessel', 'to_wellhead', 'vtd_file'].map((p) => ({ value: p, label: p }))]} />
          <Select style={{ width: 230 }} value={f.status} onChange={(v) => setF({ ...f, status: v })} options={[{ value: '', label: 'Все статусы' }, ...['Загружен', 'На рассмотрении ДЭО', 'На согласовании в ДЭО', 'На доработке', 'Завершено ДЭО'].map((s) => ({ value: s, label: s }))]} />
          <Rule code="D-TO-01" /><Rule code="D-TO-05" />
        </div>
        <Input.Search allowClear placeholder="Номер или наименование ТО" style={{ width: 280 }} onSearch={(v) => setF({ ...f, q: v })} />
      </div>
      <Table size="small" rowKey="id" loading={loading} columns={cols} dataSource={data?.items || []} scroll={{ x: 1200 }}
        pagination={{ current: page, pageSize: 20, total: data?.total || 0, onChange: setPage }} onRow={(r) => ({ onClick: () => nav(`/reports/${r.id}`), className: 'clickable-row' })} />
      <UploadWizard open={wizard} onClose={() => setWizard(false)} onDone={(card) => { setWizard(false); nav(`/reports/${card.id}`); }} />
    </div>
  );
});

export default Reports;
