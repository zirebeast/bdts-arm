// W-8.1 (Δ) Входящие интеграции: загрузка пообъектного плана (ФМ-5.1 / АСУ ТОиР или файл ХР.xlsx) → объекты X/Y/Z; журнал обменов
import { CloudDownloadOutlined, UploadOutlined } from '@ant-design/icons';
import { Button, Modal, Select, Space, Table, Upload, message } from 'antd';
import { observer } from 'mobx-react-lite';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { post, upload } from '../api';
import FlowBar from '../components/FlowBar';
import { useLoad } from '../hooks';
import { get } from '../api';
import { app } from '../store';
import { ScreenTitle, StatusChip, fmtDateTime, showError } from '../ui';

const PlanLoad = observer(() => {
  const nav = useNavigate();
  const log = useLoad(() => get('/inbound/log'), []);
  const [q, setQ] = useState({ source: 'ФМ-5.1 «Формирование планов»', year: 2027, deo: app.me!.deo || '' });
  const [modal, setModal] = useState<'' | 'select' | 'result'>('');
  const [prev, setPrev] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const can = app.can('int.load');
  const fetchPlan = async () => {
    setBusy(true);
    try { setPrev(await post('/inbound/plan/preview', q)); setModal('result'); } catch (e) { showError(e); } finally { setBusy(false); }
  };
  const accept = async () => {
    setBusy(true);
    try {
      const r = await post('/inbound/plan/accept', { rows: prev.rows, source: prev.source || q.source, year: q.year });
      message.success(`Пообъектный план загружен: новых объектов ${r.created}, обновлено ${r.updated}`);
      setModal('');
      nav('/inbound/objects');
    } catch (e) { showError(e); } finally { setBusy(false); }
  };
  return (
    <div>
      <ScreenTitle code="W-8.1" title={<>Входящие интеграции</>} sub="ДЭО получает пообъектный план (ПП) из модуля планирования ЕЦП и атрибуты ЕО из МП-3 «БДО». Загрузка не меняет утверждённый ПП: БДТС создаёт по строкам ПП объекты диагностирования X/Y/Z."
        extra={can && <>
          <Upload showUploadList={false} accept=".xlsx" customRequest={async ({ file }) => { try { setPrev(await upload('/inbound/plan/upload', { file: file as File })); setModal('result'); } catch (e) { showError(e); } }}>
            <Button icon={<UploadOutlined />}>Загрузить файл ПП (формат ХР.xlsx)</Button></Upload>
          <Button type="primary" icon={<CloudDownloadOutlined />} onClick={() => setModal('select')}>Загрузить пообъектный план</Button></>} />
      <FlowBar />
      <div className="grid g3" style={{ marginBottom: 12 }}>
        {(log.data?.cards || []).map((c: any) => (
          <div key={c.title} className="panel" style={{ marginBottom: 0 }}><b>{c.title}</b><div className="hint">{c.src}</div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6, gap: 6 }}><span className="hint">{c.last && c.last.includes('T') ? `Загружено: ${fmtDateTime(c.last)}` : c.last || 'Не загружался'}</span><StatusChip status={c.st} compact /></div></div>
        ))}
      </div>
      <Table size="small" rowKey={(_, i) => String(i)} loading={log.loading} dataSource={log.data?.log || []} title={() => <b>Журнал входящих обменов</b>} pagination={{ pageSize: 15 }}
        locale={{ emptyText: 'Обменов ещё не было. Начните с загрузки пообъектного плана.' }} columns={[
          { title: 'Дата и время', dataIndex: 'date', render: fmtDateTime }, { title: 'Поток', dataIndex: 'flow' }, { title: 'Источник', dataIndex: 'src' },
          { title: 'Записей', dataIndex: 'count', render: (v) => <span className="mono">{v}</span> }, { title: 'Результат', dataIndex: 'st', render: (s) => <StatusChip status={s} compact /> }, { title: 'Инициатор', dataIndex: 'user' }]} />
      <Modal open={modal === 'select'} title="Загрузка пообъектного плана" okText="Получить план" cancelText="Отмена" confirmLoading={busy} onOk={fetchPlan} onCancel={() => setModal('')}>
        <Space wrap>
          <div><div className="field-label">Источник</div><Select style={{ width: 280 }} value={q.source} onChange={(v) => setQ({ ...q, source: v })} options={['ФМ-5.1 «Формирование планов»', 'АСУ ТОиР (переходный период)'].map((x) => ({ value: x, label: x }))} /></div>
          <div><div className="field-label">Год плана</div><Select style={{ width: 100 }} value={q.year} onChange={(v) => setQ({ ...q, year: v })} options={[2026, 2027].map((x) => ({ value: x, label: x }))} /></div>
          <div><div className="field-label">ДЭО</div><Select style={{ width: 120 }} disabled={!!app.me!.deo} value={q.deo} onChange={(v) => setQ({ ...q, deo: v })} options={[{ value: '', label: 'Все' }, ...app.refs!.deo.map((d) => ({ value: d.code, label: d.code }))]} /></div>
        </Space>
        <p className="hint" style={{ marginTop: 10 }}>Будут получены утверждённые строки ПП вида работ «ДТОиР — диагностика». Повторная загрузка обновит существующие объекты по шифру X/Y/Z, ничего не удаляя.</p>
      </Modal>
      <Modal open={modal === 'result'} width={760} title="Результат получения пообъектного плана" onCancel={() => setModal('')}
        footer={<><Button onClick={() => setModal('')}>Закрыть</Button><Button type="primary" loading={busy} disabled={!prev?.rows?.length} onClick={accept}>Принять и перейти к объектам →</Button></>}>
        {prev && <>
          <div className="grid g4" style={{ marginBottom: 10 }}>
            {[['Строк ПП', prev.stats.rows], ['Объектов X/Y/Z', prev.stats.objects], ['Ошибок', prev.stats.errors], ['Предупреждений', prev.stats.warnings]].map(([k, v]) => (
              <div key={k} className="panel" style={{ background: '#F8FAFC', marginBottom: 0 }}><div className="hint">{k}</div><div className="mono" style={{ fontSize: 20, fontWeight: 600 }}>{v}</div></div>))}
          </div>
          <Table size="small" rowKey={(_, i) => String(i)} pagination={false} dataSource={prev.errors} locale={{ emptyText: 'Ошибок и предупреждений нет' }} columns={[
            { title: 'Строка ПП', dataIndex: 'row', render: (v) => <span className="mono">{v}</span> }, { title: 'Поле', dataIndex: 'field' }, { title: 'Значение', dataIndex: 'value', render: (v) => <span className="mono">{v}</span> },
            { title: 'Правило', dataIndex: 'rule' }, { title: 'Уровень', dataIndex: 'level', render: (l) => <StatusChip status={l === 'Ошибка' ? 'Ошибка' : 'Есть предупреждения'} compact /> }]} />
          {prev.stats.errors > 0 && <p className="hint" style={{ marginTop: 8 }}>Строка с ошибкой не загружается: исправьте шифр в модуле планирования и повторите загрузку.</p>}
        </>}
      </Modal>
    </div>
  );
});

export default PlanLoad;
