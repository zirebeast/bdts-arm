// W-2.4 (Δ) Карточка технического отчёта XSD v3.8: проверка, сопоставление ЕО с БДО, паспорт, протоколы, ведомости, фото, заключение, версии, история
import { DownloadOutlined, SendOutlined, UploadOutlined, WarningOutlined } from '@ant-design/icons';
import { Badge, Button, Card, Select, Space, Table, Tabs, Tag, message } from 'antd';
import { observer } from 'mobx-react-lite';
import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { download, get, post, put } from '../api';
import IssuesPanel from '../components/IssuesPanel';
import LoadState from '../components/LoadState';
import UploadWizard from '../components/UploadWizard';
import { useLoad } from '../hooks';
import { BackLink, DecisionModal, KV, Rule, ScreenTitle, StatusChip, fmtDate, fmtDateTime, showError } from '../ui';

const RO = '__repair__';
const STATE_RU: Record<string, string> = { normative: 'Исправное', serviceable: 'Работоспособное', limited_serviceable: 'Ограниченно работоспособное', emergency: 'Неработоспособное' };
const ADM_RU: Record<string, string> = { fit: 'Годен', not_fit: 'Не годен', corresponds: 'Соответствует', not_corresponds: 'Не соответствует' };
const CAT_RU: Record<string, string> = { project_docs: 'Проектная документация', operation_docs: 'Эксплуатационная документация', structure_defects: 'Дефекты конструкций', ecp_defects: 'Дефекты ЭХЗ', electrical_defects: 'Электрооборудование', functional_defects: 'Функциональные' };

function EoSelect({ value, deo, label, disabled, onChange, dup }: { value: any; deo: string; label: string; disabled: boolean; onChange: (v: any) => void; dup: boolean }) {
  const [opts, setOpts] = useState<any[]>([]);
  const search = async (q: string) => setOpts(await get('/refs/eo', { q, deo }));
  useEffect(() => { search(''); }, [deo]);
  const options = [{ value: RO, label: 'ОР · Объект ремонта (ЕО нет в БДО, D-TO-05)' }, ...(value && value !== RO && !opts.some((o) => o.id === value) ? [{ value, label }] : []),
    ...opts.map((o) => ({ value: o.id, label: `${o.code} · ${o.name}` }))];
  return <Select showSearch filterOption={false} onSearch={search} style={{ width: '100%', minWidth: 280 }} disabled={disabled} value={value || undefined}
    placeholder="— Не сопоставлено —" status={!value ? 'warning' : dup ? 'error' : undefined} options={options} onChange={onChange} allowClear />;
}

const ReportCard = observer(() => {
  const { id } = useParams();
  const { data: r, setData, loading, error, reload } = useLoad(() => get(`/reports/${id}`), [id]);
  const [tab, setTab] = useState('check');
  const [map, setMap] = useState<Record<number, any>>({});
  const [wizard, setWizard] = useState(false);
  const [decide, setDecide] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (r) setMap(Object.fromEntries(r.equipment.map((e: any) => [e.id, e.repairObject ? RO : e.bdoEoId]))); }, [r]);
  const TABS: Record<string, string> = { 'Проверка': 'check', 'ЕО (Сопоставление)': 'eo', 'Паспорт': 'passport', 'Протоколы': 'protocols', 'Ведомости': 'statements', 'Фото': 'photos' };

  return (
    <LoadState loading={loading} error={error} reload={reload}>{() => {
      const p = r.parsed || {};
      const v = r.validation || {};
      const dirty = r.equipment.some((e: any) => (map[e.id] ?? null) !== (e.repairObject ? RO : e.bdoEoId ?? null));
      const counts: Record<string, number> = {};
      Object.values(map).forEach((x: any) => { if (x && x !== RO) counts[x] = (counts[x] || 0) + 1; });
      const dups = Object.keys(counts).filter((k) => counts[k] > 1);
      const unmapped = r.equipment.filter((e: any) => !map[e.id]).length;
      const names: Record<string, string> = Object.fromEntries((p.equipment || []).map((e: any) => [e.uid, e.name]));
      const methods: Record<string, string> = p.methods || {};
      const saveMap = async () => {
        setBusy(true);
        try {
          setData(await put(`/reports/${r.id}/mapping`, { items: r.equipment.map((e: any) => ({ id: e.id, bdoEoId: map[e.id] && map[e.id] !== RO ? map[e.id] : null, repairObject: map[e.id] === RO })) }));
          message.success('Сопоставление сохранено');
        } catch (e) { showError(e); } finally { setBusy(false); }
      };
      const items = [
        { key: 'check', label: 'Проверка', children: <>
          <Space style={{ marginBottom: 8 }}><b>Результаты проверки XML по схеме XSD v3.8 и правилам модели</b><Rule code="OQ-07" text="L1→Block, L2→Warn, L3/L5→Info" /></Space>
          {r.source === 'Хозспособ' ? <div className="banner-info">ТО хозспособа сформирован в БДТС по данным результата ДО <Link to={`/results/${r.resultId}`}>задания</Link>; XML-проверка не требуется.</div>
            : <IssuesPanel issues={v.issues || []} onGo={(t) => setTab(TABS[t] || 'check')} />}
        </> },
        { key: 'eo', label: <Badge count={unmapped} size="small" offset={[8, -2]}>ЕО (Сопоставление)</Badge>, children: <>
          <Space wrap style={{ marginBottom: 8, justifyContent: 'space-between', width: '100%' }}>
            <span className="hint">Каждая ЕО из XML (EquipmentType) привязывается к эталонной ЕО МП-3 «БДО» для раскладки в записи о ТС (Б316)<Rule code="D-TO-04" /></span>
            {r.can.map && <Space>
              <Button onClick={async () => { try { const x = await post(`/reports/${r.id}/suggest`); setData(x); message.info(`Предложено сопоставление для ${x.matched} ЕО — проверьте перед отправкой`); } catch (e) { showError(e); } }}>Предложить сопоставление по наименованию</Button>
              <Button type="primary" disabled={!dirty} loading={busy} onClick={saveMap}>Сохранить сопоставление</Button>
            </Space>}
          </Space>
          {dups.length > 0 && <div className="banner-err">Одна ЕО БДО выбрана для нескольких ЕО отчёта. Каждой ЕО отчёта должна соответствовать своя ЕО БДО.</div>}
          <Table size="small" rowKey="id" pagination={false} dataSource={r.equipment} scroll={{ x: 1000 }} columns={[
            { title: 'ЕО в XML отчёте', dataIndex: 'name', render: (n) => <b>{n}</b> }, { title: 'Тип ЕО', dataIndex: 'type' }, { title: 'Марка стали', dataIndex: 'steel', render: (x) => <span className="mono">{x}</span> },
            { title: 'Толщина', dataIndex: 'sNom', render: (x) => <span className="mono">{x}</span> }, { title: 'Происхождение', dataIndex: 'origin', render: (x) => <Tag className="mono">{x}</Tag> },
            { title: 'Эталонная ЕО в МП-3 «БДО»', width: 360, render: (_: any, e: any) => <EoSelect value={map[e.id]} deo={r.deo} label={e.bdoLabel} disabled={!r.can.map} dup={dups.includes(String(map[e.id]))} onChange={(x) => setMap({ ...map, [e.id]: x ?? null })} /> },
          ]} />
        </> },
        { key: 'passport', label: 'Паспорт', children: <KV cols={3} items={[['Номер ТО (report_number)', <span className="mono">{r.number}</span>], ['Дата отчёта', fmtDate(r.date)], ['Профиль отчёта', r.profileName],
          ['Год обследования', p.report?.year || '—'], ['ОПО и класс опасности', r.opo?.name ? `${r.opo.name}${r.opo.hazard ? ` (${r.opo.hazard} класс опасности)` : ''}` : '—'], ['Рег. № ОПО', r.opo?.reg || '—'],
          ['Заказчик (customer)', r.customer], ['Исполнитель (executor)', r.executor], ['Применённые НТД (applied_ntd[])', (p.report?.ntd || []).join(', ') || '—'],
          ['Снимок версий НСИ (dictionary_versions)', (p.report?.dict_versions || []).join('; ') || r.dictSnapshot], ['Нумерация протоколов', p.report?.numbering || '—'], ['Строка ПП / Заказ', r.ppLine || '—']]} /> },
        { key: 'protocols', label: 'Протоколы', children: <>
          <Table size="small" rowKey={(x: any) => x.number + x.order} pagination={false} dataSource={p.protocols || []} title={() => <b>Протоколы контроля (ProtocolType)</b>} columns={[
            { title: '№ протокола', render: (_: any, x: any) => <span className="mono">{x.number}{x.number_fixed && <Tag color="blue" style={{ marginLeft: 6 }}>→ {x.number_fixed}</Tag>}</span> },
            { title: 'Метод контроля', dataIndex: 'method', render: (m) => methods[m] || m }, { title: 'Дата', dataIndex: 'date', render: fmtDate },
            { title: 'ЕО / замеры', render: (_: any, x: any) => x.rows.map((row: any, i: number) => <div key={i}>{names[row.eo] || '—'}: {row.measurements.length ? row.measurements.map((m: any) => `${m.label}=${m.value}`).join(', ') : row.defects.join('; ') || row.comment || '—'}</div>) },
          ]} />
          <Table size="small" style={{ marginTop: 12 }} rowKey={(x: any) => x.method + x.eo} pagination={false} dataSource={p.method_statuses || []} title={() => <b>Статусы проведения методов (MethodStatusType)</b>} columns={[
            { title: 'Метод', dataIndex: 'method', render: (m) => methods[m] || m }, { title: 'Статус', dataIndex: 'status', render: (s) => <StatusChip status={s === 'performed' ? 'Проведён' : 'Метод не проводился'} compact /> },
            { title: 'Причина / комментарий', render: (_: any, x: any) => [x.reason, x.reason_text, x.comment].filter(Boolean).join(' · ') || '—' }]} />
        </> },
        { key: 'statements', label: 'Ведомости', children: (p.statements || []).length ? (p.statements || []).map((s: any, i: number) => (
          <Table key={i} size="small" rowKey="no" pagination={false} dataSource={s.items} scroll={{ x: 1000 }} title={() => <b>Ведомость дефектов {s.number} от {fmtDate(s.date)} · код ОР {s.repair_code}</b>} columns={[
            { title: '№ стр.', dataIndex: 'no', width: 70 }, { title: 'ЕО отчёта', dataIndex: 'eo', render: (u) => names[u] || '—' }, { title: 'Категория', dataIndex: 'category', render: (c) => CAT_RU[c] || c },
            { title: 'Описание дефекта', dataIndex: 'text' }, { title: 'Часовая поз.', dataIndex: 'clock', render: (c) => <span className="mono">{c || '—'}</span> },
            { title: 'Допустимость', dataIndex: 'adm', render: (a) => <StatusChip status={a === 'fit' ? 'Допустимо с ремонтом' : ADM_RU[a] === 'Не годен' ? 'Ошибка' : ADM_RU[a] || a} compact /> },
            { title: 'Мероприятия', dataIndex: 'measures' }]} />)) : <div className="hint">Ведомостей в отчёте нет.</div> },
        { key: 'photos', label: 'Фото', children: <div className="grid g3">{(p.photos || []).map((ph: any) => (
          <Card key={ph.id} size="small">
            <div style={{ height: 90, background: '#E8ECF1', borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#5A6472' }} className="mono">{ph.uri || <span style={{ color: '#B42318' }}><WarningOutlined /> нет файла (V-PH-002)</span>}</div>
            <b>{ph.caption}</b><div className="hint">Привязка к ЕО: {names[ph.eo] || '—'}</div><div className="mono hint" style={{ color: '#1E7B34' }}>SHA-256: {ph.sha?.slice(0, 8)}…{ph.sha?.slice(-8)}</div>
          </Card>))}{!(p.photos || []).length && <div className="hint">Фото нет.</div>}</div> },
        { key: 'concl', label: 'Заключение и подписи', children: <div className="grid g2">
          <Card size="small" title="Заключение (ConclusionType)">{(p.conclusions || []).map((c: any, i: number) => <p key={i}>Техническое состояние: <b>{STATE_RU[c.state] || c.state || '—'}</b>. {c.text}</p>)}
            <div className="hint">Подписи: {(p.signatures || []).map((s: any) => `${s.name} (${s.role})`).join(', ') || '—'}</div></Card>
          <Card size="small" title="Раскладка 1 ТО → N записей о ТС (memo п.5)">
            {r.records.length ? <div>Сформированы записи: {r.records.map((x: any) => <Link key={x.id} to={`/ts-records/${x.id}`} style={{ marginRight: 8 }} className="mono">{x.number}</Link>)}</div>
              : <p className="hint">После решения ДЭО «Завершено ДЭО» формируются записи Б316–Б319 по всем сопоставленным ЕО отчёта ({r.eoCount - r.unmappedCount} из {r.eoCount}).</p>}
          </Card></div> },
        { key: 'files', label: 'Файлы и версии', children: <Table size="small" rowKey="version" pagination={false} dataSource={r.versions} columns={[
          { title: 'Версия', dataIndex: 'version', render: (x) => <Tag className="mono">v{x}</Tag> },
          { title: 'Файл', render: (_: any, x: any) => (x.fileId ? <a onClick={() => download(`/files/${x.fileId}`)}><DownloadOutlined /> {x.file}</a> : x.file) },
          { title: 'Вложения', render: (_: any, x: any) => x.attachments.map((a: any) => <div key={a.id}><a onClick={() => download(`/files/${a.id}`)}>{a.name}</a></div>) },
          { title: 'Ошибок L1', dataIndex: 'blocks' }, { title: 'Снимок НСИ', dataIndex: 'snapshot' }, { title: 'Загружено', render: (_: any, x: any) => `${x.by}, ${fmtDateTime(x.at)}` }]} /> },
        { key: 'history', label: 'История', children: <Table size="small" rowKey={(_, i) => String(i)} pagination={false} dataSource={[...r.history].reverse()} columns={[
          { title: 'Дата', dataIndex: 'date', render: fmtDateTime }, { title: 'Пользователь', dataIndex: 'user' }, { title: 'Статус', dataIndex: 'status', render: (s) => <StatusChip status={s} compact /> }, { title: 'Комментарий', dataIndex: 'comment' }]} /> },
      ];
      return (
        <div>
          <ScreenTitle code="W-2.4" back={<BackLink to="/reports">Реестр ТО</BackLink>}
            title={<Space wrap><span className="mono">{r.number}</span><Tag className="mono">{r.version}</Tag><StatusChip status={r.status} /></Space>}
            sub={<>Профиль: <b>{r.profileName}</b> · Снимок НСИ: <b>{r.dictSnapshot}</b> · 1 ТО → {r.eoCount} ЕО · {r.source}</>}
            extra={<>
              {r.can.upload && <Button icon={<UploadOutlined />} onClick={() => setWizard(true)}>Загрузить новую версию</Button>}
              {r.can.send && <Button type="primary" icon={<SendOutlined />} disabled={!!r.sendBlockReason || dirty} loading={busy}
                onClick={async () => { setBusy(true); try { setData(await post(`/reports/${r.id}/send`)); message.success('Технический отчёт отправлен на рассмотрение в ДЭО'); } catch (e) { showError(e); } finally { setBusy(false); } }}>Отправить в ДЭО</Button>}
              {r.can.decide && <Button type="primary" onClick={() => setDecide(true)}>Внести решение ДЭО</Button>}
            </>} />
          {r.can.send && r.sendBlockReason && <div className="hint" style={{ marginTop: -6, marginBottom: 10, textAlign: 'right' }}>Отправка недоступна: {r.sendBlockReason}</div>}
          {unmapped > 0 && <div className="banner-warn" style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
            <span><WarningOutlined /> Обнаружено <b>{unmapped} ЕО</b> без сопоставления с эталонным справочником МП-3 «БДО». Отправка в ДЭО недоступна, пока ЕО не сопоставлены<Rule code="OQ-14" />.</span>
            <Button size="small" onClick={() => setTab('eo')}>Перейти к сопоставлению →</Button></div>}
          <div className="panel"><Tabs activeKey={tab} onChange={setTab} items={items} /></div>
          <UploadWizard open={wizard} reportId={r.id} onClose={() => setWizard(false)} onDone={(card) => { setWizard(false); setData(card); setTab('check'); }} />
          <DecisionModal open={decide} title="Решение ДЭО по техническому отчёту" a="Завершено ДЭО" b="На доработку" onClose={() => setDecide(false)} rule="R-B303-05"
            onSubmit={async (d, c) => { const x = await post(`/reports/${r.id}/decision`, { decision: d === 'a' ? 'done' : 'rework', comment: c }); setData(x); message.success(d === 'a' ? `ТО завершён ДЭО, сформировано записей о ТС: ${x.records.length}` : 'ТО возвращён на доработку в ГД'); }} />
        </div>
      );
    }}</LoadState>
  );
});

export default ReportCard;
