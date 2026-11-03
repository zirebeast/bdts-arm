// W-6.1 (Δ) Реестр участков ВТД и линейная схема: контроль пересечений км и смежности (D-VTD-01), импорт из Excel с отчётом об ошибках
import { DownloadOutlined, PlusOutlined, UploadOutlined } from '@ant-design/icons';
import { Button, Input, InputNumber, Modal, Select, Space, Table, Upload, message } from 'antd';
import { observer } from 'mobx-react-lite';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { download, get, post, upload } from '../api';
import { useLoad } from '../hooks';
import { app } from '../store';
import { Rule, ScreenTitle, StatusChip, fieldErrors, showError } from '../ui';

export function LinearScheme({ items, active }: { items: any[]; active?: number }) {
  const pipes = Array.from(new Set(items.map((s) => s.pipeline)));
  const COLORS = ['#1F5FAD', '#1E7B34', '#6E56CF', '#0E7490'];
  return (
    <div>
      {pipes.map((p) => {
        const secs = items.filter((s) => s.pipeline === p);
        const max = Math.max(...secs.map((s) => s.kmTo));
        return (
          <div key={p} style={{ marginBottom: 12 }}>
            <div className="field-label">Линейная схема: {p} (0 — {max} км)</div>
            <div style={{ position: 'relative', height: 64, background: '#F4F6F8', border: '1px solid #D5DAE1', borderRadius: 6 }}>
              {secs.map((s, i) => (
                <div key={s.id} title={`${s.code}: ${s.kmFrom}–${s.kmTo} км`} style={{ position: 'absolute', top: s.overlaps?.length ? 30 : 8, height: 22, left: `${(s.kmFrom / max) * 100}%`, width: `${((s.kmTo - s.kmFrom) / max) * 100}%`,
                  background: s.overlaps?.length ? '#E07B00' : COLORS[i % COLORS.length], opacity: active && active !== s.id ? 0.45 : 1, color: '#fff', fontSize: 11, borderRadius: 4, overflow: 'hidden', whiteSpace: 'nowrap', padding: '3px 6px', boxSizing: 'border-box' }}
                  className="mono">{s.code}: {s.kmFrom}–{s.kmTo} км{s.overlaps?.length ? ' ⚠' : ''}</div>
              ))}
              {secs.flatMap((s) => s.chambers).map((c: any) => (
                <div key={c.id} title={`${c.code} (${c.km} км)`} style={{ position: 'absolute', bottom: 2, left: `calc(${(c.km / max) * 100}% - 5px)`, width: 10, height: 10, borderRadius: c.kind === 'launch' ? 2 : 10, background: c.active ? '#1B1F24' : '#9AA3AE' }} />
              ))}
            </div>
            <div className="hint">■ камера запуска · ● камера приёма СОД · оранжевый — пересечение границ</div>
          </div>
        );
      })}
    </div>
  );
}

const Vtd = observer(() => {
  const nav = useNavigate();
  const { data, loading, reload } = useLoad(() => get('/vtd'), []);
  const [form, setForm] = useState<any>(null);
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [imp, setImp] = useState<any>(null);
  const can = app.can('vtd.edit');
  return (
    <div>
      <ScreenTitle code="W-6.1" title={<>Реестр участков ВТД и линейная схема</>} sub={<>Контроль пересечений км и смежности участков, камеры запуска и приёма СОД<Rule code="D-VTD-01" /></>} extra={<>
        <Button icon={<DownloadOutlined />} onClick={() => download('/vtd/template.xlsx')}>Шаблон Excel</Button>
        {can && <Upload showUploadList={false} accept=".xlsx" customRequest={async ({ file }) => { try { const r = await upload('/vtd/import', { file: file as File }); setImp(r); reload(); } catch (e) { showError(e); } }}><Button icon={<UploadOutlined />}>Импорт участков из Excel</Button></Upload>}
        {can && <Button type="primary" icon={<PlusOutlined />} onClick={() => { setErrs({}); setForm({ code: '', pipeline: 'МГ «Север–Юг» нитка I', kmFrom: 0, kmTo: 10, type: 'Подземный', deo: 'ОРГ_9', adjacent: '' }); }}>Создать участок</Button>}
      </>} />
      {data && <div className="panel"><LinearScheme items={data.items} /></div>}
      {data?.items?.some((s: any) => s.overlaps.length) && <div className="banner-warn">Обнаружены пересечения границ участков: {data.items.filter((s: any) => s.overlaps.length).map((s: any) => `${s.code} ↔ ${s.overlaps.join(', ')}`).join('; ')}. Скорректируйте границы.</div>}
      <Table size="small" rowKey="id" loading={loading} dataSource={data?.items || []} pagination={false} onRow={(r) => ({ onClick: () => nav(`/vtd/${r.id}`), className: 'clickable-row' })} columns={[
        { title: 'Код участка', dataIndex: 'code', render: (v) => <b className="mono" style={{ color: '#1F5FAD' }}>{v}</b> }, { title: 'Магистральный газопровод (ТМ)', dataIndex: 'pipeline' },
        { title: 'Км начала – Км конца', render: (_: any, r: any) => <span className="mono" style={{ color: r.overlaps.length ? '#B54708' : undefined, fontWeight: r.overlaps.length ? 600 : 400 }}>{r.kmFrom} – {r.kmTo} км</span> },
        { title: 'Тип участка', dataIndex: 'type' }, { title: 'Камеры СОД', render: (_: any, r: any) => r.chambers.map((c: any) => `${c.code} (${c.km} км${c.permanent ? '' : ', врем.'}${c.active ? '' : ', снята'})`).join(' → ') },
        { title: 'Смежный участок', dataIndex: 'adjacent', render: (v) => v || '—' }, { title: 'Статус границ', dataIndex: 'status', render: (s) => <StatusChip status={s} compact /> }]} />
      <Modal open={!!form} title="Участок ВТД" okText="Сохранить" cancelText="Отмена" onCancel={() => setForm(null)} onOk={async () => {
        try { await post('/vtd', form); message.success('Участок сохранён'); setForm(null); reload(); } catch (e) { setErrs(fieldErrors(e)); showError(e); }
      }}>
        {form && <Space direction="vertical" style={{ width: '100%' }}>
          <div><div className="field-label">Код участка <span className="req">*</span></div><Input value={form.code} status={errs.code ? 'error' : undefined} onChange={(e) => setForm({ ...form, code: e.target.value })} /></div>
          <div><div className="field-label">Магистральный газопровод <span className="req">*</span></div><Input value={form.pipeline} onChange={(e) => setForm({ ...form, pipeline: e.target.value })} /></div>
          <Space><div><div className="field-label">Км начала</div><InputNumber value={form.kmFrom} onChange={(v) => setForm({ ...form, kmFrom: v })} /></div>
            <div><div className="field-label">Км конца</div><InputNumber value={form.kmTo} status={errs.kmTo ? 'error' : undefined} onChange={(v) => setForm({ ...form, kmTo: v })} /></div></Space>
          {errs.kmTo && <div className="err">{errs.kmTo}</div>}
          <div><div className="field-label">Тип участка</div><Select style={{ width: '100%' }} value={form.type} onChange={(v) => setForm({ ...form, type: v })} options={(data?.types || []).map((t: string) => ({ value: t, label: t }))} /></div>
          <div><div className="field-label">Смежный участок</div><Select allowClear style={{ width: '100%' }} value={form.adjacent || undefined} onChange={(v) => setForm({ ...form, adjacent: v || '' })} options={(data?.items || []).map((s: any) => ({ value: s.code, label: s.code }))} /></div>
        </Space>}
      </Modal>
      <Modal open={!!imp} title="Результат импорта участков" onCancel={() => setImp(null)} footer={<Button onClick={() => setImp(null)}>Закрыть</Button>}>
        {imp && <>
          <div className="banner-info">Загружено участков: {imp.created}. Ошибок: {imp.errors.length}. Пересечений: {imp.overlaps.length}.</div>
          {imp.errors.map((e: any) => <div key={e.row} className="err">Строка {e.row} ({e.code}): {e.error}</div>)}
          {imp.overlaps.map((o: any) => <div key={o.code} style={{ color: '#B54708' }}>{o.code}: пересечение с {o.with.join(', ')}</div>)}
        </>}
      </Modal>
    </div>
  );
});

export default Vtd;
