// W-4.2 (Δ) Дашборды по ролям D1–D5: показатели считаются по данным хранилища (витрина Б320); каждый показатель открывает список-источник
import { Card, Segmented, Select, Space, Table } from 'antd';
import { observer } from 'mobx-react-lite';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { get } from '../api';
import LoadState from '../components/LoadState';
import { useLoad } from '../hooks';
import { app } from '../store';
import { ScreenTitle, fmtDate, fmtDateTime, fmtNum } from '../ui';

const MONTHS = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'];
const VID_COLORS = ['#1F5FAD', '#5B8FD0', '#8DB3E2', '#B8CFEC', '#DCE7F5'];
const STATE_COLORS = ['#2E7D32', '#8BC34A', '#E07B00', '#C62828'];
const ROLE_TAB: Record<string, string> = { 'BDTS.PLANNER': 'D1', 'BDTS.OTVTS': 'D2', 'BDTS.OTVTECHOT': 'D3', 'BDTS.TO_UPLOAD': 'D4' };

function Kpi({ label, value, sub, mark, go }: { label: string; value: any; sub?: string; mark?: 'ok' | 'bl' | 'ex'; go?: string }) {
  const nav = useNavigate();
  return (
    <button className="kpi" onClick={() => go && nav(go)}>
      <div className="hint">{mark && <span style={{ color: mark === 'ex' ? '#C62828' : mark === 'bl' ? '#B45F00' : '#2E7D32' }}>{mark === 'ex' ? '◆ ' : mark === 'bl' ? '▲ ' : '● '}</span>}{label}</div>
      <div className="v">{value}</div>
      {sub && <div className="hint">{sub}</div>}
      {go && <div style={{ color: '#1F5FAD', fontSize: 12, marginTop: 4 }}>Открыть список →</div>}
    </button>
  );
}

function Bars({ data, color, max }: { data: [string, number][]; color?: (i: number) => string; max?: number }) {
  const m = max || Math.max(1, ...data.map((d) => d[1]));
  return (
    <div className="bar-chart" role="img" aria-label={data.map(([l, v]) => `${l}: ${v}`).join('; ')}>
      {data.map(([l, v], i) => (
        <div key={l} className="col"><span className="mono" style={{ fontSize: 11 }}>{v}</span>
          <div style={{ width: '100%', height: `${Math.max(2, (v / m) * 80)}%`, background: color ? color(i) : '#1F5FAD', borderRadius: '3px 3px 0 0' }} />
          <span className="lbl">{l}</span></div>
      ))}
    </div>
  );
}

const Dashboards = observer(() => {
  const nav = useNavigate();
  const def = ['BDTS.PLANNER', 'BDTS.OTVTS', 'BDTS.OTVTECHOT', 'BDTS.TO_UPLOAD'].map((c) => (app.hasRole(c) ? ROLE_TAB[c] : '')).find(Boolean) || 'D1';
  const [tab, setTab] = useState(def);
  const [deo, setDeo] = useState('');
  const [eoId, setEoId] = useState<number | undefined>();
  const { data: d, loading, error, reload } = useLoad(() => get(`/dashboards/${tab}`, { deo, eo_id: eoId }), [tab, deo, eoId]);
  const TABS = [['D1', 'Планирование диагностики'], ['D2', 'Состояние оборудования'], ['D3', 'Планирование ремонта'], ['D4', 'Технические отчёты'], ['D5', 'ЕО 360°']];
  return (
    <div>
      <ScreenTitle code="W-4.2" title={<>Дашборды по ролям</>} sub="Дашборды для ролей, которые планируют диагностику и ремонт. Каждый показатель открывает список-источник."
        extra={!app.me!.deo && <Space><span className="hint">ДЭО</span><Select style={{ width: 160 }} value={deo} onChange={setDeo} options={[{ value: '', label: 'Все ДЭО' }, ...app.refs!.deo.map((x) => ({ value: x.code, label: x.code }))]} /></Space>} />
      <div className="toolbar"><Segmented value={tab} onChange={(v) => setTab(v as string)} options={TABS.map(([k, l]) => ({ value: k, label: `${k}. ${l}` }))} /></div>
      <LoadState loading={loading} error={error} reload={reload}>{() => (
        <>
          {tab === 'D1' && <>
            <div className="grid g4" style={{ marginBottom: 12 }}>
              <Kpi label="ЕО со сроком ТД ≤ 12 мес." value={d.kpi.due12} sub="по последней записи Б316" go="/planning" />
              <Kpi label="Просрочено ТД" value={d.kpi.overdue} sub="без активного задания Б301" mark="ex" go="/planning" />
              <Kpi label="ЕО без данных о сроке" value={d.kpi.noData} sub="нет записи о ТС" mark="bl" go="/hierarchy" />
              <Kpi label="Покрытие ПП заданиями" value={`${d.kpi.coverage} %`} sub={d.kpi.coverageText} go="/inbound/objects" />
            </div>
            <div className="grid" style={{ gridTemplateColumns: '2fr 1fr', marginBottom: 12 }}>
              <Card size="small" title={`Календарь нагрузки ${d.year}: ЕО к ТД по месяцам`} extra={<span className="hint">Б301, Б316</span>}>
                <div className="bar-chart" style={{ height: 190 }}>
                  {d.load.map((seg: number[], i: number) => {
                    const tot = seg.reduce((a, b) => a + b, 0);
                    const mx = Math.max(d.capacity * 1.4, ...d.load.map((s: number[]) => s.reduce((a, b) => a + b, 0)), 1);
                    return <div key={i} className="col"><span className="mono" style={{ fontSize: 11, color: tot > d.capacity ? '#C62828' : undefined }}>{tot}</span>
                      <div style={{ width: '100%', height: `${(tot / mx) * 82}%`, display: 'flex', flexDirection: 'column-reverse', borderRadius: '3px 3px 0 0', overflow: 'hidden' }}>
                        {seg.map((v, j) => <div key={j} style={{ height: `${tot ? (v / tot) * 100 : 0}%`, background: VID_COLORS[j] }} />)}</div>
                      <span className="lbl">{MONTHS[i]}</span></div>;
                  })}
                </div>
                <Space wrap className="hint">{['ТПА', 'Сосуды', 'ФА и КГ', 'ГРС', 'ВТД'].map((v, j) => <span key={v}><span style={{ display: 'inline-block', width: 10, height: 10, background: VID_COLORS[j], marginRight: 4 }} />{v}</span>)}
                  <span style={{ color: '#C62828' }}>Мощность бригад: {d.capacity} ЕО/мес. (настройка W-7.1)</span></Space>
              </Card>
              <Card size="small" title="Карта сроков: ДЭО × квартал" extra={<span className="hint">Б316</span>}>
                <table style={{ width: '100%', textAlign: 'center', borderCollapse: 'separate', borderSpacing: 2 }}><thead><tr className="hint"><th style={{ textAlign: 'left' }}>ДЭО</th>{['I', 'II', 'III', 'IV'].map((q) => <th key={q}>{q} кв.</th>)}</tr></thead>
                  <tbody>{d.heat.map(([deoCode, vals, over]: any) => <tr key={deoCode}><td style={{ textAlign: 'left' }}><b>{deoCode}</b></td>{vals.map((v: number, i: number) => (
                    <td key={i}><div className="mono" style={{ padding: '6px 0', borderRadius: 4, background: `rgba(31,95,173,${0.1 + Math.min(v, 12) / 16})`, color: v > 6 ? '#fff' : '#1B1F24' }}>{v}{over[i] > 0 && <span style={{ color: '#FFD5D0', marginLeft: 3 }}>◆{over[i]}</span>}</div></td>))}</tr>)}</tbody></table>
                <div className="hint">Число ЕО к ТД; ◆ — просроченные.</div>
              </Card>
            </div>
            <div className="grid g2">
              <Card size="small" title="Кандидаты на сокращение объёма ДО" extra={<a onClick={() => nav('/planning')}>Отбор к планированию →</a>}>
                <Table size="small" pagination={false} rowKey={(r: any) => r[0]} dataSource={d.lessScope} locale={{ emptyText: 'Нет кандидатов' }} columns={[{ title: 'ЕО', dataIndex: 0 }, { title: 'ТС', dataIndex: 1 }, { title: 'Ресурс', dataIndex: 2 }, { title: 'Предложение', dataIndex: 3 }]} />
              </Card>
              <Card size="small" title="Кандидаты на внеочередное ДО">
                <Table size="small" pagination={false} rowKey={(r: any) => r[0]} dataSource={d.moreScope} locale={{ emptyText: 'Нет кандидатов' }} columns={[{ title: 'ЕО', dataIndex: 0 }, { title: 'Причина', dataIndex: 1 }, { title: 'Ресурс', dataIndex: 2 }]} />
              </Card>
            </div>
          </>}
          {tab === 'D2' && <>
            <div className="grid g4" style={{ marginBottom: 12 }}>
              <Kpi label="ЕО под контролем" value={d.kpi.controlled} sub="есть запись Б316" go="/ts-records" />
              <Kpi label="Ухудшение ТС" value={d.kpi.worse} sub="хуже предыдущей оценки" mark="ex" go="/ts-records" />
              <Kpi label="Ресурс < 7 лет" value={d.kpi.life7} sub={`из них < 2 лет: ${d.kpi.life2}`} mark="bl" go="/hierarchy" />
              <Kpi label="Требует подтверждения" value={d.kpi.confirm} sub="записи Б316" go="/ts-records?confirm=Требует подтверждения" />
            </div>
            <div className="grid g2" style={{ marginBottom: 12 }}>
              <Card size="small" title="Распределение по техническому состоянию, %" extra={<span className="hint">Б316</span>}>
                {Object.entries(d.dist).map(([cls, parts]: any) => (
                  <div key={cls} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}><span style={{ width: 130 }}>{cls}</span>
                    <div style={{ flex: 1, display: 'flex', height: 20, borderRadius: 4, overflow: 'hidden', background: '#EEF1F4' }}>{parts.map((p: number, i: number) => <div key={i} style={{ width: `${p}%`, background: STATE_COLORS[i], color: '#fff', fontSize: 10, textAlign: 'center', lineHeight: '20px' }}>{p >= 8 ? `${p}%` : ''}</div>)}</div></div>))}
                <Space wrap className="hint">{['Исправное', 'Работоспособное', 'Огр. работоспособное', 'Неработоспособное'].map((l, i) => <span key={l}><span style={{ display: 'inline-block', width: 10, height: 10, background: STATE_COLORS[i], marginRight: 4 }} />{l}</span>)}</Space>
              </Card>
              <Card size="small" title="Остаточный ресурс: распределение ЕО" extra={<span className="hint">расчёт ресурса</span>}>
                <Bars data={d.life.map(([l, v]: any) => [`${l} лет`, v])} color={(i) => (i === 0 ? '#C62828' : i < 3 ? '#E07B00' : '#1F5FAD')} />
              </Card>
            </div>
            <Card size="small" title="Топ ОПО по риску" extra={<span className="hint">Б316, Б319</span>}>
              <Table size="small" pagination={false} rowKey={(r: any) => r[0]} dataSource={d.risk} onRow={() => ({ onClick: () => nav('/hierarchy'), className: 'clickable-row' })} columns={[
                { title: 'ОПО', dataIndex: 0 }, { title: 'ДЭО', dataIndex: 1 }, { title: 'Дефекты ◆', dataIndex: 2, render: (v) => <span className="mono" style={{ color: '#C62828' }}>{v}</span> },
                { title: 'Дефекты ▲', dataIndex: 3, render: (v) => <span className="mono" style={{ color: '#B45F00' }}>{v}</span> }, { title: 'Ресурс < 2 лет', dataIndex: 4 }, { title: 'Балл', dataIndex: 5, render: (v) => <b className="mono">{v}</b> }]} />
            </Card>
          </>}
          {tab === 'D3' && <>
            <div className="grid g4" style={{ marginBottom: 12 }}>
              <Kpi label="Дефекты без мероприятия" value={d.kpi.noMeasure} sub="открытые сообщения Б319" mark="ex" go="/ts-records" />
              <Kpi label="Записи с мероприятиями КР/ТОиР" value={d.kpi.inPlan} sub="включено в план" />
              <Kpi label="Отремонтировано, ждёт подтверждения ТС" value={d.kpi.awaitConfirm} sub="ИД получена, Б316 не подтверждена" mark="bl" go="/ts-records?confirm=Требует подтверждения" />
              <Kpi label="Повторные дефекты" value={d.kpi.repeat} sub="та же категория на ЕО" />
            </div>
            <div className="grid g2" style={{ marginBottom: 12 }}>
              <Card size="small" title="Воронка дефектов" extra={<span className="hint">Б319, Б316</span>}>
                {d.funnel.map(([l, v]: any, i: number) => <div key={l} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}><span style={{ width: 160 }}>{l}</span>
                  <div style={{ flex: 1 }}><div className="mono" style={{ width: `${Math.max(4, (v / Math.max(1, d.funnel[0][1])) * 100)}%`, background: '#1F5FAD', opacity: 1 - i * 0.13, color: '#fff', borderRadius: 4, padding: '2px 8px', fontSize: 12 }}>{v}</div></div></div>)}
              </Card>
              <Card size="small" title="Возраст бэклога (дефекты без устранения)"><Bars data={d.ages} color={(i) => (i === 3 ? '#C62828' : i === 2 ? '#E07B00' : '#1F5FAD')} /></Card>
            </div>
            <Card size="small" title="Срочность устранения">
              <Table size="small" pagination={{ pageSize: 8 }} rowKey={(r: any) => r.recordId + r.defect} dataSource={d.urgent} onRow={(r: any) => ({ onClick: () => nav(`/ts-records/${r.recordId}`), className: 'clickable-row' })} columns={[
                { title: 'Дефект', dataIndex: 'defect' }, { title: 'ЕО', dataIndex: 'eo' }, { title: 'Мероприятие', dataIndex: 'measure' }, { title: 'Предельный срок', dataIndex: 'deadline', render: fmtDate },
                { title: 'Дней', dataIndex: 'days', render: (v) => <span className="mono" style={{ color: v < 45 ? '#C62828' : undefined, fontWeight: v < 45 ? 600 : 400 }}>{v}</span> }]} />
            </Card>
          </>}
          {tab === 'D4' && <>
            <div className="grid" style={{ gridTemplateColumns: 'repeat(5, minmax(0,1fr))', marginBottom: 12 }}>
              {d.statuses.map(([s, n]: any) => <Kpi key={s} label={s} value={n} go="/reports" />)}
            </div>
            <div className="grid g3" style={{ marginBottom: 12 }}>
              <Kpi label="Просрочка рассмотрения ДЭО" value={d.kpi.overdue} sub="дольше норматива этапа (5 раб. дней)" mark="ex" go="/reports" />
              <Kpi label="Доля возвратов" value={`${d.kpi.returnShare} %`} sub="ТО возвращены хотя бы раз" mark="bl" />
              <Kpi label="ЕО отчётов без сопоставления с БДО" value={d.kpi.unmapped} sub="D-TO-04" mark="bl" go="/reports" />
            </div>
            <Card size="small" title="Замечания XML по правилам ФЛК (Парето)" extra={<span className="hint">версии ТО</span>}>
              {d.pareto.map(([c, t, n]: any) => <div key={c + t} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}><span className="mono" style={{ width: 90 }}>{c}</span><span style={{ width: 360 }}>{t}</span>
                <div style={{ flex: 1 }}><div style={{ height: 14, background: '#5B8FD0', borderRadius: 3, width: `${(n / Math.max(1, d.pareto[0][2])) * 100}%` }} /></div><span className="mono">{n}</span></div>)}
              {!d.pareto.length && <span className="hint">Замечаний нет</span>}
            </Card>
          </>}
          {tab === 'D5' && (d.eo ? <>
            <div className="toolbar">
              <div><div className="hint">ЕО</div><Select showSearch optionFilterProp="label" style={{ width: 460, maxWidth: '100%' }} value={d.eo.id} onChange={setEoId} options={d.options.map((o: any) => ({ value: o.id, label: o.label }))} />
                <div className="hint">{d.eo.tmName} · ТМ {d.eo.tm} · БДО: {d.eo.sync === 'synced' ? 'синхронизирована' : d.eo.sync}</div></div>
              <Space wrap>
                <span className={`tol ${(['Ограниченно работоспособное', 'Неработоспособное'].includes(d.eo.state)) ? 'tol-ex' : 'tol-bl'}`}>{d.eo.state || '—'}</span>
                <span className={`tol ${d.eo.life !== null && d.eo.life < 3 ? 'tol-ex' : 'tol-ok'}`}>Ресурс {fmtNum(d.eo.life, 1)} лет</span>
                <span className="tol tol-em">След. ТД: {fmtDate(d.eo.next)}</span>
              </Space>
            </div>
            <div className="grid" style={{ gridTemplateColumns: '2fr 1fr', marginBottom: 12 }}>
              <Card size="small" title="Минимальная толщина стенки по годам (Б318, УЗТ)">
                {d.thickness.length >= 1 ? (() => {
                  const pts = d.thickness as [number, number][];
                  const ys = pts.map((p) => p[1]).concat(d.eo.sCalc ? [d.eo.sCalc] : []);
                  const lo = Math.min(...ys) * 0.95; const hi = Math.max(...ys) * 1.05;
                  const x0 = pts[0][0]; const x1 = Math.max(pts[pts.length - 1][0] + 1, x0 + 2);
                  const X = (y: number) => 50 + ((y - x0) / (x1 - x0)) * 520; const Y = (v: number) => 190 - ((v - lo) / (hi - lo || 1)) * 170;
                  return <svg viewBox="0 0 600 220" style={{ width: '100%' }} role="img" aria-label="Динамика минимальной толщины">
                    {d.eo.sCalc && <><line x1="40" x2="590" y1={Y(d.eo.sCalc)} y2={Y(d.eo.sCalc)} stroke="#C62828" strokeDasharray="5 4" /><text x="586" y={Y(d.eo.sCalc) - 6} textAnchor="end" fontSize="11" fill="#C62828">s расч. = {fmtNum(d.eo.sCalc, 1)} мм</text></>}
                    <polyline fill="none" stroke="#1F5FAD" strokeWidth="2.5" points={pts.map(([y, v]) => `${X(y)},${Y(v)}`).join(' ')} />
                    {pts.map(([y, v]) => <g key={y}><circle cx={X(y)} cy={Y(v)} r="5" fill={d.eo.sCalc && v < d.eo.sCalc * 1.08 ? '#E07B00' : '#2E7D32'} /><text x={X(y)} y={Y(v) - 10} textAnchor="middle" fontSize="11">{fmtNum(v)}</text><text x={X(y)} y="212" textAnchor="middle" fontSize="11" fill="#5A6472">{y}</text></g>)}
                  </svg>;
                })() : <span className="hint">Нет замеров толщины</span>}
                <div className="hint">{d.rate !== null ? `Средняя скорость утонения ${fmtNum(d.rate, 3)} мм/год.` : 'Недостаточно повторных замеров для расчёта скорости коррозии.'}</div>
              </Card>
              <Card size="small" title="Хронология">
                <ul className="timeline">{d.timeline.map((t: any, i: number) => <li key={i}><span className="mono hint">{fmtDate(t.date)}</span><div style={{ color: t.bad ? '#C62828' : undefined }}><a onClick={() => nav(`/ts-records/${t.recordId}`)} style={{ color: 'inherit' }}>{t.text}</a></div></li>)}</ul>
              </Card>
            </div>
            <div className="grid g2">
              <Card size="small" title="Открытые дефекты (Б319)"><Table size="small" pagination={false} rowKey={(_, i) => String(i)} dataSource={d.openDefects} locale={{ emptyText: 'Нет' }} columns={[
                { title: '', dataIndex: 'crit', width: 30, render: (c) => <span style={{ color: c === 'Высокая' ? '#C62828' : '#B45F00' }}>{c === 'Высокая' ? '◆' : '▲'}</span> }, { title: 'Дефект', dataIndex: 'text' }, { title: 'Статус', dataIndex: 'fix' }]} /></Card>
              <Card size="small" title="Ракурсы по ролям"><ul style={{ paddingLeft: 18, margin: 0 }}><li><b>Планировщик ДО:</b> сроки ТД, история ДО, кандидат на внеочередное ДО</li><li><b>Ремонт:</b> дефекты, мероприятия, ИД ремонтов</li><li><b>Контроль ТС:</b> все ракурсы, подтверждение ТС после ремонта</li></ul>
                <a onClick={() => nav(`/eo/${d.eo.id}`)}>Открыть карточку ЕО →</a></Card>
            </div>
          </> : <div className="panel">Нет ЕО в области данных.</div>)}
          <div className="hint" style={{ textAlign: 'right', marginTop: 8 }}>данные на {fmtDateTime(d.stamp)} (витрина Б320)</div>
        </>
      )}</LoadState>
    </div>
  );
});

export default Dashboards;
