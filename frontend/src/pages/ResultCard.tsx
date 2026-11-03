// W-2.2 Карточка результата ДО (п. 4.4.7 ТПР): разделы ПЭ/КП, допуски, переходы статусов, ЭПБ, ВТД, выгрузка ТО
import { CheckOutlined, DeleteOutlined, DownloadOutlined, HistoryOutlined, LockOutlined, PaperClipOutlined, PlusOutlined } from '@ant-design/icons';
import { Button, Checkbox, DatePicker, Input, Modal, Radio, Segmented, Select, Space, Table, Tag, message } from 'antd';
import dayjs from 'dayjs';
import { observer } from 'mobx-react-lite';
import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { download, get, post, put } from '../api';
import LoadState from '../components/LoadState';
import { useLoad, useUnsavedGuard } from '../hooks';
import { pointTol, secStatus, secTolList, tolField, tolRow } from '../sections';
import { app } from '../store';
import { BackLink, Block, DecisionModal, FilePick, HistoryModal, KV, Rule, ScreenTitle, SecBadge, StatusChip, TolBadge, fmtDate, showError } from '../ui';

type Mode = 'view' | 'pe' | 'kp';
const clone = (x: any) => JSON.parse(JSON.stringify(x));

function TwoBtn({ opts, value, onChange, disabled }: { opts: string[]; value: string; onChange: (v: string) => void; disabled: boolean }) {
  return <Radio.Group optionType="button" buttonStyle="solid" size="small" value={value || undefined} disabled={disabled} onChange={(e) => onChange(e.target.value)} options={opts.map((o) => ({ label: o, value: o }))} />;
}

function Fields({ sec, d, ed, set }: { sec: any; d: any; ed: boolean; set: (p: any) => void }) {
  return (
    <div className="grid g2">
      {sec.fields.map((f: any) => {
        const v = d.values?.[f.key] ?? '';
        const t = f.tol ? tolField(f.tol, v) : null;
        const setV = (val: string) => set({ values: { ...d.values, [f.key]: val } });
        return (
          <div key={f.key} style={{ gridColumn: f.type === 'textarea' ? '1 / -1' : undefined }}>
            <div className="field-label">{f.label} {f.req && <span className="req">*</span>}</div>
            <Space wrap style={{ width: '100%' }} styles={{ item: (f.type === 'select' && f.opts.length > 2) || f.type === 'textarea' || f.type === 'text' ? { flex: 1, minWidth: 220 } : {} }}>
              {f.type === 'select' && f.opts.length === 2 ? <TwoBtn opts={f.opts} value={v} onChange={setV} disabled={!ed} />
                : f.type === 'select' ? <Select style={{ width: '100%' }} disabled={!ed} value={v || undefined} placeholder="Выберите…" options={f.opts.map((o: string) => ({ value: o, label: o }))} onChange={setV} />
                  : f.type === 'textarea' ? <Input.TextArea rows={3} maxLength={1000} showCount disabled={!ed} value={v} onChange={(e) => setV(e.target.value)} />
                    : f.type === 'date' ? <DatePicker format="DD.MM.YYYY" disabled={!ed} value={v ? dayjs(v) : null} onChange={(x) => setV(x ? x.format('YYYY-MM-DD') : '')} />
                      : <Input className={f.type === 'num' ? 'mono' : ''} inputMode={f.type === 'num' ? 'decimal' : undefined} style={{ width: f.type === 'num' ? 140 : '100%' }} disabled={!ed} value={v} onChange={(e) => setV(e.target.value)} />}
              {t && t !== 'empty' && <TolBadge t={t} />}
            </Space>
          </div>
        );
      })}
    </div>
  );
}

function SectionBody({ sec, d, ed, edBase, set, res, eo, canConcl }: { sec: any; d: any; ed: boolean; edBase: boolean; set: (p: any) => void; res: any; eo: any; canConcl: boolean }) {
  if (sec.kind === 'info') {
    const t = res.task;
    return <div><div className="hint" style={{ marginBottom: 8 }}>Справочные данные. Редактируемых полей нет.</div>
      <KV items={[['Вид ДО', t.vidDo], ['Объект ДО', t.eoName], ['Единица оборудования', eo?.eoId ? <Link to={`/eo/${eo.eoId}`}>{eo.label}</Link> : eo?.label], ['Местоположение', t.location],
        ['Эксплуатирующая организация', t.deo], ['Бригада', t.brigade], ['Шаблон', t.template], ...((eo?.passport || []) as [string, string][])]} /></div>;
  }
  const tols = secTolList(sec, d);
  return (
    <div>
      {sec.stage === 'ПЭ' && sec.instrument && (
        <div className="panel" style={{ background: '#F8FAFC', display: 'flex', gap: 24, flexWrap: 'wrap' }}>
          <div><div className="field-label">Прибор (Б314)</div><b>{sec.instrument}</b></div>
          <div><div className="field-label">Заводской № прибора</div><Input className="mono" style={{ width: 180 }} disabled={!ed} value={d.serial} placeholder="А12-550192" onChange={(e) => set({ serial: e.target.value })} /></div>
          <div><div className="field-label">Специалист (Б306)</div><b>ФИО_3, УД-8812-23</b></div>
        </div>
      )}
      {sec.stage === 'ПЭ' && (
        <Space style={{ marginBottom: 12 }}>
          <Checkbox disabled={!edBase} checked={d.np} onChange={(e) => set({ np: e.target.checked })}>Метод не проводился <span className="hint">(C-16)</span></Checkbox>
          {d.np && <Select style={{ width: 240 }} disabled={!edBase} value={d.reason || undefined} placeholder="Причина…" onChange={(v) => set({ reason: v })}
            options={['Объект не остановлен', 'Не применимо', 'Не входит в объём', 'Иное'].map((x) => ({ value: x, label: x }))} />}
        </Space>
      )}
      {d.np ? <div className="banner-info">Метод не проводился{d.reason ? ` (${d.reason})` : ''}. Протокол по методу формироваться не будет (V-MS-001).</div> : (
        <>
          {sec.kind === 'form' && <Fields sec={sec} d={d} ed={ed} set={set} />}
          {sec.kind === 'checklist' && (
            <Table size="small" pagination={false} rowKey={(r: any) => r[0]} dataSource={sec.items} columns={[
              { title: 'Код', dataIndex: 0, width: 110, render: (v) => <span className="mono">{v}</span> },
              { title: 'Категория осмотра', dataIndex: 1 },
              { title: 'Результат', render: (_: any, [code, name, opts]: any) => {
                const idx = d.items?.[code] ?? -1;
                const tol = idx >= 0 ? opts[idx][1] : 'empty';
                const setIdx = (i: number) => set({ items: { ...d.items, [code]: i } });
                return <div>
                  {opts.length === 2 ? <TwoBtn opts={opts.map((o: any) => o[0])} value={idx >= 0 ? opts[idx][0] : ''} disabled={!ed} onChange={(o) => setIdx(opts.findIndex((x: any) => x[0] === o))} />
                    : <Select style={{ width: 230 }} disabled={!ed} value={idx >= 0 ? idx : undefined} placeholder="Выберите…" options={opts.map((o: any, i: number) => ({ value: i, label: o[0] }))} onChange={setIdx} />}
                  {(tol === 'borderline' || tol === 'exceeded') && <Input style={{ marginTop: 4 }} disabled={!ed} placeholder="Описание, локализация и размеры" value={d.notes?.[code] || ''}
                    onChange={(e) => set({ notes: { ...d.notes, [code]: e.target.value } })} aria-label={`Описание: ${name}`} />}
                </div>;
              } },
              { title: 'Допуск', width: 130, render: (_: any, [code, , opts]: any) => { const idx = d.items?.[code] ?? -1; return <TolBadge t={idx >= 0 ? opts[idx][1] : 'empty'} />; } },
            ]} />
          )}
          {sec.kind === 'points' && (
            <div>
              {d.elements.map((el: any, ei: number) => {
                const cfg = sec.elements[ei] || {};
                const lo = cfg.lo ?? sec.lo;
                const hi = cfg.hi ?? sec.hi;
                const filled = el.points.filter((p: any) => p.value).length;
                const setPts = (points: any[]) => set({ elements: d.elements.map((x: any, i: number) => (i === ei ? { ...x, points } : x)) });
                return (
                  <div key={el.name} style={{ border: '1px solid #D5DAE1', borderRadius: 6, marginBottom: 10 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 10px', background: '#F8FAFC', borderBottom: '1px solid #D5DAE1', flexWrap: 'wrap', gap: 6 }}>
                      <span><b>{el.name}</b> <span className="hint">{sec.mode === 'thk' ? `s расч. = ${Number(cfg.s).toFixed(1)} мм` : `норма ${lo}–${hi} HB`} · точек контроля: {filled} из {el.points.length}</span></span>
                      {ed && <Button size="small" icon={<PlusOutlined />} onClick={() => setPts([...el.points, { id: `${ei}-${Date.now()}`, label: `Т${el.points.length + 1}`, value: '', extra: true }])}>Добавить точку контроля</Button>}
                    </div>
                    <div className="points-grid">
                      {el.points.map((p: any) => {
                        const t = pointTol(sec, ei, p.value);
                        return (
                          <div key={p.id} className={`point tol-${t === 'ok' ? 'ok' : t === 'borderline' ? 'bl' : t === 'exceeded' ? 'ex' : 'em'}`}>
                            <span className="mono" style={{ width: 28 }}>{p.label}</span>
                            <Input size="small" className="mono" inputMode="decimal" style={{ width: 72 }} disabled={!ed} value={p.value} aria-label={`${el.name}, ${p.label}`}
                              onChange={(e) => setPts(el.points.map((q: any) => (q.id === p.id ? { ...q, value: e.target.value } : q)))} />
                            <span title={t}>{({ ok: '●', borderline: '▲', exceeded: '◆', empty: '—' } as any)[t]}</span>
                            {p.extra && ed && <DeleteOutlined style={{ color: '#B42318', marginLeft: 'auto', cursor: 'pointer' }} onClick={() => setPts(el.points.filter((q: any) => q.id !== p.id))} />}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
              <div className="hint">{sec.mode === 'thk' ? 'Допуск: меньше s расч. — ◆ вне допуска; до 1,08·s расч. — ▲ на границе; иначе ● в допуске.' : 'Допуск: вне диапазона HB — ◆; в пределах 8 HB от границы — ▲; иначе ●.'}</div>
            </div>
          )}
          {sec.kind === 'table' && (
            <div>
              <Table size="small" pagination={false} rowKey="id" dataSource={d.rows} scroll={{ x: 700 }} locale={{ emptyText: 'Строк нет' }} columns={[
                ...sec.cols.map((c: any) => ({ title: c.label, key: c.key, render: (_: any, r: any) => {
                  const setCell = (v: string) => set({ rows: d.rows.map((x: any) => (x.id === r.id ? { ...x, [c.key]: v } : x)) });
                  return c.type === 'select' && c.opts.length === 2 ? <TwoBtn opts={c.opts} value={r[c.key]} onChange={setCell} disabled={!ed} />
                    : c.type === 'select' ? <Select style={{ minWidth: 200, width: '100%' }} disabled={!ed} value={r[c.key] || undefined} placeholder="Выберите…" options={c.opts.map((o: string) => ({ value: o, label: o }))} onChange={setCell} />
                      : <Input className={c.type === 'num' ? 'mono' : ''} inputMode={c.type === 'num' ? 'decimal' : undefined} disabled={!ed} value={r[c.key] || ''} onChange={(e) => setCell(e.target.value)} />;
                } })),
                { title: 'Оценка', width: 130, render: (_: any, r: any) => <TolBadge t={tolRow(sec.tol, r)} /> },
                ...(ed ? [{ title: '', width: 40, render: (_: any, r: any) => <DeleteOutlined style={{ color: '#B42318', cursor: 'pointer' }} onClick={() => set({ rows: d.rows.filter((x: any) => x.id !== r.id) })} /> }] : []),
              ]} />
              {ed && <Button size="small" icon={<PlusOutlined />} style={{ marginTop: 8 }} onClick={() => set({ rows: [...d.rows, { id: Date.now(), ...Object.fromEntries(sec.cols.map((c: any) => [c.key, ''])) }] })}>{sec.code === 'doc' ? 'Добавить документ' : 'Добавить строку'}</Button>}
              {sec.note && <div className="hint" style={{ marginTop: 6 }}>{sec.note}</div>}
              {sec.fields && <div style={{ marginTop: 12 }}><Fields sec={sec} d={d} ed={ed} set={set} /></div>}
            </div>
          )}
        </>
      )}
      <div style={{ borderTop: '1px solid #D5DAE1', marginTop: 14, paddingTop: 12 }}>
        <Space wrap style={{ marginBottom: 8 }}>
          <span className="hint">Фото и файлы:</span>
          {(d.photos || []).map((p: any) => <Tag key={p.id || p} icon={<PaperClipOutlined />} closable={ed} onClose={() => set({ photos: d.photos.filter((x: any) => x !== p) })}>
            {p.id ? <a onClick={() => download(`/files/${p.id}`)}>{p.name}</a> : String(p)}</Tag>)}
          {!(d.photos || []).length && <span className="hint">нет</span>}
          {ed && <FilePick label="Добавить фото" accept=".jpg,.jpeg,.png,.pdf" entityType="do_result" entityId={String(res.id)} onUploaded={(f) => set({ photos: [...(d.photos || []), { id: f.id, name: f.name }] })} />}
        </Space>
        <div className="field-label">Комментарий <Rule code="R-B303-08" /></div>
        <Input.TextArea rows={2} maxLength={1000} showCount disabled={!edBase} value={d.comment} onChange={(e) => set({ comment: e.target.value })} />
        {sec.stage === 'ПЭ' && <>
          <div className="field-label" style={{ marginTop: 8 }}>Заключение специалиста по разделу <span className="req">*</span></div>
          <Input.TextArea rows={2} maxLength={1000} disabled={!edBase || !canConcl} value={d.concl} placeholder="Вывод по результатам контроля" onChange={(e) => set({ concl: e.target.value })} />
        </>}
      </div>
      {tols.filter((x) => x === 'exceeded').length > 0 && sec.kind !== 'info' && <div className="hint" style={{ marginTop: 8, color: '#C62828' }}>◆ Вне допуска в разделе: {tols.filter((x) => x === 'exceeded').length}</div>}
    </div>
  );
}

const ResultCard = observer(() => {
  const { id } = useParams();
  const { data: res, setData, loading, error, reload } = useLoad(() => get(`/results/${id}`), [id]);
  const [eoIdx, setEoIdx] = useState(0);
  const [code, setCode] = useState('');
  const [mode, setMode] = useState<Mode>('view');
  const [drafts, setDrafts] = useState<Record<string, any>>({});
  const [modal, setModal] = useState('');
  const [busy, setBusy] = useState(false);
  const [epbFile, setEpbFile] = useState<any>(null);
  const [vtdFiles, setVtdFiles] = useState<any[]>([]);
  const [comment, setComment] = useState('');
  const [epbNeed, setEpbNeed] = useState<'a' | 'b'>('a');
  const dirty = Object.keys(drafts).length > 0;
  useUnsavedGuard(dirty);
  useEffect(() => { if (res && !code && res.sections.length) setCode(res.sections.find((s: any) => s.kind !== 'info')?.code || res.sections[0].code); }, [res]);

  const dataOf = (i: number, c: string) => drafts[`${i}|${c}`] ?? res?.data?.[String(i)]?.[c];
  const numbered = useMemo(() => (res?.sections || []).filter((s: any) => s.kind !== 'info'), [res]);
  const title = (s: any) => (s.kind === 'info' ? s.title : `${numbered.indexOf(s) + 1}. ${s.title}`);

  const run = async (action: string, body: any = {}, ok?: string) => {
    setBusy(true);
    try {
      const r = await post(`/results/${id}/actions/${action}`, { version: res.version, ...body });
      setData(r);
      if (ok) message.success(ok);
      setModal('');
      app.loadNotes();
    } catch (e: any) { showError(e); if (e.status === 409) reload(); } finally { setBusy(false); }
  };

  const save = async () => {
    setBusy(true);
    try {
      let r = res;
      for (const [k, v] of Object.entries(drafts)) {
        const [i, c] = k.split('|');
        r = await put(`/results/${id}/sections/${c}`, { eo_idx: Number(i), data: v, version: r.version });
      }
      setData(r);
      setDrafts({});
      setMode('view');
      message.success(mode === 'pe' ? 'Измерения ПЭ сохранены' : 'Данные КП сохранены');
    } catch (e: any) { showError(e); if (e.status === 409) { setDrafts({}); setMode('view'); reload(); } } finally { setBusy(false); }
  };
  const cancel = () => {
    if (dirty) Modal.confirm({ title: 'Есть несохранённые изменения', content: 'Отменить ввод? Изменения будут потеряны.', okText: 'Отменить ввод', cancelText: 'Продолжить ввод', onOk: () => { setDrafts({}); setMode('view'); } });
    else setMode('view');
  };

  return (
    <LoadState loading={loading} error={error} reload={reload}>{() => {
      const t = res.task;
      const sec = res.sections.find((s: any) => s.code === code) || res.sections[0];
      const peSecs = res.sections.filter((s: any) => s.stage === 'ПЭ');
      const kpSecs = res.sections.filter((s: any) => s.stage === 'КП');
      const stOf = (s: any) => secStatus(s, dataOf(eoIdx, s.code));
      const lastFix = [...res.history].reverse().find((h: any) => h.status === 'На корректировке');
      const edBase = !!sec && sec.kind !== 'info' && ((sec.stage === 'ПЭ' && mode === 'pe') || (sec.stage === 'КП' && mode === 'kp'));
      const d = sec ? dataOf(eoIdx, sec.code) : null;
      const setSec = (p: any) => setDrafts((m) => ({ ...m, [`${eoIdx}|${sec.code}`]: { ...clone(dataOf(eoIdx, sec.code)), ...p } }));
      const locked = (s: any) => s.kind !== 'info' && (s.stage === 'ПЭ' ? res.status !== 'ПЭ не завершен' : !['Требуется КП', 'На корректировке'].includes(res.status));
      const onAction = (a: any) => {
        if (a.key === 'pe') { setMode('pe'); if (sec?.stage !== 'ПЭ' || sec.kind === 'info') setCode(peSecs.find((s: any) => s.kind !== 'info')?.code); return; }
        if (a.key === 'kp') { setMode('kp'); if (sec?.stage !== 'КП') setCode(kpSecs[0]?.code); return; }
        if (a.key === 'pe_finish') return run('pe_finish', {}, 'Полевой этап завершён: результат ДО — «Требуется КП», задание — «Полевой этап завершен»');
        if (a.key === 'form') return run('form', {}, res.exceeded ? `Технический отчёт сформирован (.docx). ${res.exceeded} результатов вне допуска — проверьте заключение` : 'Технический отчёт сформирован (.docx)');
        if (a.key === 'send') return run('send', {}, 'Результат ДО отправлен на согласование');
        setComment(''); setEpbFile(null); setVtdFiles([]); setEpbNeed('a');
        setModal(a.key);
      };
      return (
        <div>
          <ScreenTitle code={t.isHs ? 'W-2.5' : 'W-2.2'} back={<BackLink to={t.isHs ? '/hs' : `/results?vid=${t.vid}`}>К списку результатов</BackLink>}
            title={<Space wrap>Результат ДО по заданию № {t.id}<StatusChip status={res.status} />
              {mode !== 'view' && <Tag color="blue">{mode === 'pe' ? 'Ввод данных ПЭ' : 'Ввод данных КП'}</Tag>}</Space>} />
          <Block title="Информация о результате ДО" extra={<Link to={`/tasks/${t.id}`}>Задание на ДО № {t.id} · <StatusChip status={t.status} compact /></Link>}>
            <KV cols={4} items={[['Вид ДО', t.vidDo], ['XYZ', <span className="mono">{t.xyz}</span>], ['Объект ДО', t.eoName], ['Эксплуатирующая организация', t.deo],
              ['Местоположение', t.location], ['Бригада', t.brigade], ['Плановое начало ДО', fmtDate(t.startDate)], ['Плановое завершение ДО', fmtDate(t.endDate)]]} />
          </Block>
          {res.status === 'Результат получен' && <div className="banner-ok">Результат получен. Данные о техническом состоянии обновлены: созданы записи о ТС (Б316) по ЕО результата. <Link to={`/ts-records?q=`}>Открыть реестр записей о ТС →</Link></div>}
          {res.status === 'На корректировке' && lastFix && <div className="banner-warn"><b>Возвращено на корректировку:</b> {lastFix.comment}</div>}
          <div className="toolbar">
            <Space wrap>
              <span className="field-label" style={{ margin: 0, textTransform: 'uppercase' }}>Управление результатом ДО</span>
              {mode !== 'view' ? <>
                <Button type="primary" icon={<CheckOutlined />} loading={busy} onClick={save} style={{ background: '#1E7B34' }}>Сохранить</Button>
                <Button onClick={cancel}>Отмена</Button>
              </> : <>
                {res.actions.map((a: any) => <Button key={a.key} type={a.primary ? 'primary' : 'default'} disabled={a.disabled} loading={busy && !a.primary} onClick={() => onAction(a)}>{a.label}</Button>)}
                {res.exports.map((e: any) => <Button key={e.key} icon={<DownloadOutlined />} onClick={() => (e.key === 'export_vtd' ? res.vtdFiles.forEach((f: any) => download(`/results/${id}/export`, { kind: `vtd${f.id}` })) : download(`/results/${id}/export`, { kind: ({ export_epb: 'epb', export_xml: 'to_xml' } as Record<string, string>)[e.key] || 'to' }))}>{e.label}</Button>)}
                {!res.actions.length && !res.exports.length && <span className="hint">Для вашей роли в статусе «{res.status}» действий нет.</span>}
              </>}
            </Space>
            <Button icon={<HistoryOutlined />} onClick={() => setModal('history')}>История</Button>
            {mode === 'view' && res.hints.map((h: string) => <div key={h} className="hint" style={{ width: '100%' }}>{h}</div>)}
            {!res.isVtd && res.toFormed && <div className="hint" style={{ width: '100%', color: '#1E7B34' }}>Технический отчёт сформирован: {res.toFile?.name}</div>}
          </div>
          {res.isVtd ? (
            <Block title="Технический отчёт по ВТД">
              <p className="hint">Для вида ДО «ВТД» блок «Результаты» не отображается: технический отчёт загружается в результат ДО файлом (до 2 файлов).</p>
              {res.vtdFiles.length ? res.vtdFiles.map((f: any) => <div key={f.id}><PaperClipOutlined /> <a onClick={() => download(`/files/${f.id}`)}>{f.name}</a></div>) : <div className="hint">Файлы не загружены</div>}
            </Block>
          ) : (
            <>
              {res.eos.length > 1 && (
                <div className="toolbar">
                  <Space wrap><span className="hint">{t.vid === 'grs' ? 'ЕО площадки:' : 'Единица оборудования:'}</span>
                    {res.eos.map((e: any) => <Button key={e.idx} disabled={mode !== 'view'} type={eoIdx === e.idx ? 'primary' : 'default'} ghost={eoIdx === e.idx} onClick={() => setEoIdx(e.idx)}>{e.label}</Button>)}
                  </Space>
                </div>
              )}
              <div className="split">
                <nav className="panel sec-nav" aria-label="Разделы результата ДО">
                  <b>Результаты</b>
                  {[['Полевой этап', peSecs], ['Камеральная проверка', kpSecs]].map(([ttl, secs]: any) => (
                    <div key={ttl} style={{ marginTop: 8 }}>
                      <div className="field-label" style={{ display: 'flex', justifyContent: 'space-between' }}><span>{ttl}</span>
                        <span>{secs.filter((s: any) => s.kind !== 'info' && ['done', 'skipped'].includes(stOf(s))).length}/{secs.filter((s: any) => s.kind !== 'info').length}</span></div>
                      {secs.map((s: any) => {
                        const exc = secTolList(s, dataOf(eoIdx, s.code)).filter((x) => x === 'exceeded').length;
                        return (
                          <button key={s.code} className={`sec-item ${sec.code === s.code ? 'active' : ''}`} onClick={() => setCode(s.code)} aria-current={sec.code === s.code}>
                            <span style={{ minWidth: 0 }}><span style={{ display: 'block' }}>{title(s)}{drafts[`${eoIdx}|${s.code}`] ? ' •' : ''}</span>{!s.req && s.kind !== 'info' && <span className="hint">по программе</span>}</span>
                            <span style={{ display: 'flex', gap: 4, alignItems: 'center', flexShrink: 0 }}>
                              {exc > 0 && <span style={{ color: '#C62828', fontSize: 12 }} title="Результатов вне допуска">◆{exc}</span>}
                              {locked(s) && <LockOutlined style={{ color: '#5A6472' }} title="Раздел заблокирован" />}
                              {s.kind !== 'info' && <SecBadge s={stOf(s)} />}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  ))}
                  <div className="hint" style={{ borderTop: '1px solid #EEF1F4', marginTop: 8, paddingTop: 8 }}>Статус раздела: ○ не начат · ◐ в процессе · ✓ пройден · ⊘ не проводился<br />Допуск: ● в допуске · ▲ на границе · ◆ вне допуска</div>
                </nav>
                <section className="panel">
                  {sec && <>
                    <Space wrap style={{ borderBottom: '1px solid #D5DAE1', paddingBottom: 8, marginBottom: 12, width: '100%' }}>
                      <Tag>{sec.stage === 'ПЭ' ? 'Полевой этап' : 'Камеральная проверка'}</Tag><b>{title(sec)}</b>{sec.kind !== 'info' && <SecBadge s={stOf(sec)} />}
                    </Space>
                    {sec.stage === 'КП' && res.status === 'ПЭ не завершен' && <div className="banner-info">Раздел заполняется на камеральном этапе — после завершения ПЭ.</div>}
                    {d && <SectionBody sec={sec} d={d} ed={edBase && !d.np} edBase={edBase} set={setSec} res={res} eo={res.eos[eoIdx]} canConcl={res.can.concl} />}
                    {res.exceeded > 0 && sec.code === 'conclusion' && <div className="banner-err" style={{ marginTop: 12 }}>◆ {res.exceeded} результатов вне допуска — отразите их в заключении.</div>}
                  </>}
                </section>
              </div>
            </>
          )}
          <HistoryModal open={modal === 'history'} onClose={() => setModal('')} rows={res.history} withFile title="История изменения статуса результата ДО" />
          <DecisionModal open={modal === 'agree' || modal === 'deo'} title={modal === 'agree' ? 'Внесение результата согласования результата ДО' : 'Внесение результата рассмотрения ДЭО'}
            a={modal === 'agree' ? 'Согласовано' : 'Принят ДЭО'} b="Отправить на корректировку" rule="R-B303-05" onClose={() => setModal('')}
            onSubmit={async (dd, c) => { await run(modal, { decision: dd, comment: c }, dd === 'a' ? (modal === 'agree' ? 'Технический отчёт согласован и передан на рассмотрение ДЭО' : 'Результат ДО принят ДЭО') : 'Результат ДО отправлен на корректировку'); }} />
          <Modal open={modal === 'epb_need'} title="Определение необходимости в ЭПБ" okText="Отправить" cancelText="Отмена" confirmLoading={busy} onCancel={() => setModal('')}
            onOk={() => run('epb_need', { decision: epbNeed }, epbNeed === 'a' ? 'Установлен статус «Требуется ЭПБ»' : 'Статус «Результат получен», задание на ДО — «Выполнено»')}>
            <Segmented block value={epbNeed} onChange={(v) => setEpbNeed(v as any)} options={[{ label: 'ЭПБ требуется', value: 'a' }, { label: 'ЭПБ не требуется', value: 'b' }]} />
          </Modal>
          <Modal open={modal === 'epb'} title="Внесение результата ЭПБ" okText="Отправить" cancelText="Отмена" confirmLoading={busy} onCancel={() => setModal('')}
            onOk={() => (epbFile ? run('epb', { file_id: epbFile.id, comment }, res.status === 'Результат получен' ? 'Файл ЭПБ заменён, статус не изменился' : 'Результат ЭПБ внесён: «Результат получен», задание — «Выполнено»') : message.error('Выберите файл'))}>
            <Space direction="vertical" style={{ width: '100%' }}>
              <Space><FilePick accept=".pdf,.docx,.sig,.zip" entityType="do_result" entityId={String(res.id)} onUploaded={setEpbFile} /><span className={epbFile ? '' : 'hint'}>{epbFile?.name || 'Файл не выбран'}</span></Space>
              <div className="hint">Прикладывается ровно 1 файл заключения ЭПБ<Rule code="R-B303-06" />. {res.status === 'Результат получен' && 'Повторная загрузка заменит ранее приложенный файл без смены статуса.'}</div>
              <div className="field-label">Комментарий</div>
              <Input.TextArea rows={2} maxLength={1000} value={comment} onChange={(e) => setComment(e.target.value)} />
            </Space>
          </Modal>
          <Modal open={modal === 'vtd_upload'} title="Загрузка технического отчёта по ВТД" okText="Отправить" cancelText="Отмена" confirmLoading={busy} onCancel={() => setModal('')}
            okButtonProps={{ disabled: !vtdFiles.length }} onOk={() => run('vtd_upload', { file_ids: vtdFiles.map((f) => f.id), comment }, 'Технический отчёт по ВТД сохранён')}>
            <Space direction="vertical" style={{ width: '100%' }}>
              <FilePick disabled={vtdFiles.length >= 2} accept=".pdf,.xlsx,.xml,.zip,.docx" entityType="do_result" entityId={String(res.id)} onUploaded={(f) => setVtdFiles((l) => [...l, f])} />
              {vtdFiles.map((f) => <div key={f.id} className="mono"><PaperClipOutlined /> {f.name}</div>)}
              <div className="hint">Можно прикрепить до 2 файлов<Rule code="R-B303-07" />. Повторная загрузка заменяет файлы без смены статуса.</div>
              <div className="field-label">Комментарий</div>
              <Input.TextArea rows={2} maxLength={1000} value={comment} onChange={(e) => setComment(e.target.value)} />
            </Space>
          </Modal>
        </div>
      );
    }}</LoadState>
  );
});

export default ResultCard;
