// W-8.2 (Δ) Объекты диагностирования X/Y/Z: список по строкам ПП, создание объекта вне плана (isLocal)
import { PlusOutlined } from '@ant-design/icons';
import { Button, Input, Modal, Progress, Segmented, Select, Table, Tag, message } from 'antd';
import { observer } from 'mobx-react-lite';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { get, post } from '../api';
import FlowBar from '../components/FlowBar';
import { useLoad } from '../hooks';
import { app } from '../store';
import { ScreenTitle, StatusChip, fieldErrors, fmtDate, showError } from '../ui';

const EMPTY = { facilityType: '', name: '', commissionYear: '', regNumber: '', cipher: '', hazardClass: '', address: '' };
const TYPES = ['ГРС', 'КС', 'УКПГ', 'ДКС', 'Магистральный газопровод', 'Газопровод-отвод'];

const Objects = observer(() => {
  const nav = useNavigate();
  const [status, setStatus] = useState('Все');
  const [q, setQ] = useState('');
  const [page, setPage] = useState(1);
  const { data, loading } = useLoad(() => get('/inbound/objects', { status, q, page, size: 20 }), [status, q, page]);
  const [form, setForm] = useState<any>(null);
  const [errs, setErrs] = useState<Record<string, string>>({});
  const dirty = form && Object.values(form).some((v) => String(v).trim());
  const close = () => (dirty ? Modal.confirm({ title: 'Отменить создание объекта?', content: 'Введённые данные не будут сохранены.', okText: 'Отменить создание', cancelText: 'Продолжить ввод', onOk: () => setForm(null) }) : setForm(null));
  const F = (k: string, label: string, el: React.ReactNode, req = true) => <div><div className="field-label">{label} {req && <span className="req">*</span>}</div>{el}{errs[k] && <div className="err">{errs[k]}</div>}</div>;
  return (
    <div>
      <ScreenTitle code="W-8.2" title={<>Объекты диагностирования X/Y/Z</>} extra={app.can('int.load') && <Button type="primary" icon={<PlusOutlined />} onClick={() => { setErrs({}); setForm({ ...EMPTY }); }}>Создать объект ДО вне плана</Button>} />
      <FlowBar />
      <div className="toolbar">
        <Segmented value={status} onChange={(v) => { setStatus(v as string); setPage(1); }} options={['Все', 'Не начато', 'В работе', 'Завершено']} />
        <Input.Search allowClear placeholder="Шифр X/Y/Z или ОПО" style={{ width: 280 }} onSearch={(v) => { setQ(v); setPage(1); }} />
      </div>
      <Table size="small" rowKey="id" loading={loading} dataSource={data?.items || []} pagination={{ current: page, pageSize: 20, total: data?.total || 0, onChange: setPage }}
        locale={{ emptyText: <span>Объектов нет. <a onClick={() => nav('/inbound/plan')}>Загрузите пообъектный план</a> или создайте объект вне плана.</span> }}
        onRow={(r) => ({ onClick: () => nav(`/inbound/objects/${r.id}`), className: 'clickable-row' })} columns={[
          { title: 'Шифр задания', dataIndex: 'cipher', render: (v) => <b className="mono" style={{ color: '#1F5FAD' }}>{v}</b> },
          { title: 'Наименование ОПО', dataIndex: 'name', render: (v, r: any) => <span>{v}{r.local && <Tag color="orange" style={{ marginLeft: 6 }}>Локальное</Tag>}</span> },
          { title: 'Тип', dataIndex: 'type' }, { title: 'ДЭО', dataIndex: 'deo' },
          { title: 'Вид работ (строка ПП)', render: (_: any, r: any) => <div>{r.vid}<div className="mono hint">{r.ppRow}</div></div> },
          { title: 'Дата обследования', dataIndex: 'date', render: fmtDate },
          { title: 'Прогресс ЕО', width: 180, render: (_: any, r: any) => (r.total ? <Progress size="small" percent={Math.round((r.done / r.total) * 100)} format={() => `${r.done}/${r.total}`} /> : <span className="hint">ЕО нет</span>) },
          { title: 'Статус', dataIndex: 'status', render: (s) => <StatusChip status={s} compact /> }]} />
      <Modal open={!!form} width={680} title="Создание объекта диагностирования вне плана (X/Y/Z)" okText="Сохранить объект →" cancelText="Отмена" onCancel={close}
        onOk={async () => { try { const o = await post('/inbound/objects', form); message.success('Объект создан (признак «Локальное»)'); setForm(null); nav(`/inbound/objects/${o.id}`); } catch (e) { setErrs(fieldErrors(e)); showError(e); } }}>
        {form && <div className="grid g2">
          {F('facilityType', 'Тип сооружения', <Select style={{ width: '100%' }} value={form.facilityType || undefined} placeholder="Выберите…" status={errs.facilityType ? 'error' : undefined} onChange={(v) => setForm({ ...form, facilityType: v })} options={TYPES.map((x) => ({ value: x, label: x }))} />)}
          {F('cipher', 'Шифр задания (X/Y/Z)', <Input className="mono" value={form.cipher} placeholder="97475/12/101000305198" status={errs.cipher ? 'error' : undefined} onChange={(e) => setForm({ ...form, cipher: e.target.value })} />)}
          <div style={{ gridColumn: '1 / -1' }}>{F('name', 'Наименование ОПО', <Input maxLength={250} value={form.name} status={errs.name ? 'error' : undefined} onChange={(e) => setForm({ ...form, name: e.target.value })} />)}</div>
          {F('commissionYear', 'Год ввода в эксплуатацию', <Input className="mono" inputMode="numeric" value={form.commissionYear} status={errs.commissionYear ? 'error' : undefined} onChange={(e) => setForm({ ...form, commissionYear: e.target.value })} />)}
          {F('regNumber', 'Инвентарный / рег. № ОПО', <Input className="mono" value={form.regNumber} placeholder="А45-01928-001" status={errs.regNumber ? 'error' : undefined} onChange={(e) => setForm({ ...form, regNumber: e.target.value })} />)}
          {F('hazardClass', 'Класс опасности ОПО', <Select style={{ width: '100%' }} value={form.hazardClass || undefined} placeholder="Выберите…" status={errs.hazardClass ? 'error' : undefined} onChange={(v) => setForm({ ...form, hazardClass: v })}
            options={[['I', 'чрезвычайно высокая'], ['II', 'высокая'], ['III', 'средняя'], ['IV', 'низкая']].map(([v, l]) => ({ value: v, label: `${v} — ${l} опасность` }))} />)}
          {F('address', 'Адрес / местоположение', <Input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />, false)}
        </div>}
      </Modal>
    </div>
  );
});

export default Objects;
