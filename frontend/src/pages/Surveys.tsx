// W-3.8 (Δ) Опросные листы по ЕО объектов X/Y/Z: конструктор, опросы, запросы на расхождение с БДО (D-HS-01, D-DISC-01)
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import { Button, Checkbox, Input, Segmented, Select, Space, Table, message } from 'antd';
import { observer } from 'mobx-react-lite';
import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { get, post, put } from '../api';
import { useLoad } from '../hooks';
import { app } from '../store';
import { FilePick, Rule, ScreenTitle, StatusChip, fmtDate, showError } from '../ui';

const TYPES = ['Текст', 'Число', 'Дата', 'Выбор из списка', 'Да / Нет', 'Фото'];
const ATTRS = ['—', 'Заводской номер', 'Год изготовления', 'DN', 'PN', 'Марка стали', 's расчётная', 'Изготовитель'];

const Surveys = observer(() => {
  const [sp] = useSearchParams();
  const [tab, setTab] = useState(sp.get('tab') === 'disc' ? 'Запросы на расхождения' : 'Опросы по ЕО объекта');
  const can = app.can('survey');
  const tpls = useLoad(() => get('/survey-templates'), []);
  const objects = useLoad(() => get('/inbound/objects', { size: 200 }), []);
  const disc = useLoad(() => get('/discrepancies'), [tab]);
  const [tplId, setTplId] = useState<number | null>(null);
  const [draft, setDraft] = useState<any>(null);
  const [objId, setObjId] = useState<number | null>(null);
  const surveys = useLoad(() => (objId ? get('/surveys', { object_id: objId }) : Promise.resolve([])), [objId]);
  const [svId, setSvId] = useState<number | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  useEffect(() => { if (!objId && objects.data?.items?.length) setObjId((objects.data.items.find((o: any) => o.cipher === '97488/5/142000099120') || objects.data.items[0]).id); }, [objects.data]);
  useEffect(() => { const t = (tpls.data || []).find((x: any) => x.id === tplId) || (tpls.data || [])[0]; if (t) { setTplId(t.id); setDraft(JSON.parse(JSON.stringify(t))); } }, [tpls.data, tplId]);
  const sv = (surveys.data || []).find((s: any) => s.id === svId);
  useEffect(() => { setAnswers(sv?.answers || {}); }, [svId, surveys.data]);
  const published = (tpls.data || []).filter((t: any) => t.status === 'Опубликован');
  const [genTpl, setGenTpl] = useState<number | null>(null);

  const saveTpl = async (publish = false) => {
    try {
      const body = { name: draft.name, cls: draft.cls, questions: draft.questions, publish };
      const r = draft.id ? await put(`/survey-templates/${draft.id}`, body) : await post('/survey-templates', body);
      message.success(publish ? 'Шаблон опубликован и доступен для опросов' : 'Шаблон опросного листа сохранён');
      await tpls.reload();
      setTplId(r.id);
    } catch (e) { showError(e); }
  };
  const tplOfSv = sv ? (tpls.data || []).find((t: any) => t.id === sv.templateId) : null;

  return (
    <div>
      <ScreenTitle code="W-3.8" title={<>Опросные листы по ЕО объектов X/Y/Z</>} extra={<Segmented value={tab} onChange={(v) => setTab(v as string)} options={['Конструктор опросов', 'Опросы по ЕО объекта', 'Запросы на расхождения']} />} />
      {tab === 'Конструктор опросов' && draft && (
        <div className="split">
          <div className="panel sec-nav">
            <div style={{ display: 'flex', justifyContent: 'space-between' }}><b>Шаблоны опросов</b>{can && <Button size="small" icon={<PlusOutlined />} onClick={() => setDraft({ name: 'Новый опросный лист', cls: 'Все классы ЕО', status: 'Черновик', questions: [] })}>Создать</Button>}</div>
            {(tpls.data || []).map((t: any) => <button key={t.id} className={`sec-item ${draft.id === t.id ? 'active' : ''}`} onClick={() => setTplId(t.id)}>
              <span><span style={{ display: 'block' }}>{t.name}</span><span className="hint">{t.cls} · вопросов: {t.questions.length}</span></span><StatusChip status={t.status} compact /></button>)}
          </div>
          <div className="panel">
            <Space wrap style={{ width: '100%', marginBottom: 10 }}>
              <div><div className="field-label">Наименование опросного листа</div><Input style={{ width: 380 }} disabled={!can} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></div>
              <div><div className="field-label">Класс ЕО</div><Select style={{ width: 220 }} disabled={!can} value={draft.cls} onChange={(v) => setDraft({ ...draft, cls: v })} options={['Все классы ЕО', 'ТПА', 'Сосуды и аппараты', 'ФА и КГ'].map((x) => ({ value: x, label: x }))} /></div>
            </Space>
            <Table size="small" rowKey="id" pagination={false} dataSource={draft.questions} locale={{ emptyText: 'Вопросов нет' }} columns={[
              { title: '№', width: 40, render: (_: any, __: any, i: number) => i + 1 },
              { title: 'Вопрос', render: (_: any, q: any) => <Input disabled={!can} value={q.text} onChange={(e) => setDraft({ ...draft, questions: draft.questions.map((x: any) => (x.id === q.id ? { ...x, text: e.target.value } : x)) })} /> },
              { title: 'Тип ответа', width: 170, render: (_: any, q: any) => <Select style={{ width: '100%' }} disabled={!can} value={q.type} options={TYPES.map((x) => ({ value: x, label: x }))} onChange={(v) => setDraft({ ...draft, questions: draft.questions.map((x: any) => (x.id === q.id ? { ...x, type: v } : x)) })} /> },
              { title: 'Атрибут ЕО (БДО)', width: 180, render: (_: any, q: any) => <Select style={{ width: '100%' }} disabled={!can} value={q.attr} options={ATTRS.map((x) => ({ value: x, label: x }))} onChange={(v) => setDraft({ ...draft, questions: draft.questions.map((x: any) => (x.id === q.id ? { ...x, attr: v } : x)) })} /> },
              { title: 'Обяз.', width: 60, render: (_: any, q: any) => <Checkbox disabled={!can} checked={q.req} onChange={(e) => setDraft({ ...draft, questions: draft.questions.map((x: any) => (x.id === q.id ? { ...x, req: e.target.checked } : x)) })} /> },
              ...(can ? [{ title: '', width: 40, render: (_: any, q: any) => <DeleteOutlined style={{ color: '#B42318' }} onClick={() => setDraft({ ...draft, questions: draft.questions.filter((x: any) => x.id !== q.id) })} /> }] : [])]} />
            {can && <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 10 }}>
              <Button size="small" icon={<PlusOutlined />} onClick={() => setDraft({ ...draft, questions: [...draft.questions, { id: `q${Date.now()}`, text: '', type: 'Текст', attr: '—', req: false }] })}>Добавить вопрос</Button>
              <Space><Button onClick={() => saveTpl(false)}>Сохранить</Button><Button type="primary" onClick={() => saveTpl(true)}>Опубликовать</Button></Space></div>}
          </div>
        </div>
      )}
      {tab === 'Опросы по ЕО объекта' && (
        <>
          <div className="toolbar">
            <Space wrap>
              <div><div className="field-label">Объект X/Y/Z</div><Select style={{ width: 380 }} value={objId} onChange={(v) => { setObjId(v); setSvId(null); }} options={(objects.data?.items || []).map((o: any) => ({ value: o.id, label: `${o.cipher} · ${o.name}` }))} /></div>
              <div><div className="field-label">Опросный лист</div><Select style={{ width: 300 }} value={genTpl ?? published[0]?.id} onChange={setGenTpl} options={published.map((t: any) => ({ value: t.id, label: t.name }))} /></div>
              {can && <Button type="primary" style={{ marginTop: 18 }} onClick={async () => {
                try { const r = await post('/surveys/generate', { objectId: objId, templateId: genTpl ?? published[0]?.id }); message[r.created ? 'success' : 'info'](r.created ? `Сформировано опросов: ${r.created}` : 'Опросы по всем ЕО объекта уже сформированы'); surveys.reload(); } catch (e) { showError(e); }
              }}>Сформировать опросы по ЕО объекта</Button>}
            </Space>
            {objId && <Link to={`/inbound/objects/${objId}`}>Карточка объекта (W-8.3) →</Link>}
          </div>
          <div className="split" style={{ gridTemplateColumns: '7fr 5fr' }}>
            <Table size="small" rowKey="id" loading={surveys.loading} dataSource={surveys.data || []} pagination={false}
              locale={{ emptyText: 'Опросов по объекту нет. Выберите опросный лист и сформируйте опросы по ЕО.' }}
              onRow={(r) => ({ onClick: () => setSvId(r.id), className: 'clickable-row', style: r.id === svId ? { background: '#E3EEFB' } : undefined })} columns={[
                { title: 'Единица оборудования', dataIndex: 'eo' }, { title: 'Опросный лист', dataIndex: 'template' }, { title: 'Ответственный', dataIndex: 'owner' },
                { title: 'Срок', dataIndex: 'due', render: fmtDate }, { title: 'Заполнено', render: (_: any, r: any) => <span className="mono">{r.filled}/{r.total}</span> }, { title: 'Статус', dataIndex: 'status', render: (s) => <StatusChip status={s} compact /> }]} />
            <div className="panel">
              {!sv ? <span className="hint">Выберите опрос в таблице, чтобы заполнить ответы.</span> : (() => {
                const editable = can && sv.status !== 'Принят';
                const missing = (tplOfSv?.questions || []).filter((q: any) => q.req && !String(answers[q.id] || '').trim());
                return <>
                  <b>{sv.eo}</b> <span className="mono hint">{sv.eoCode}</span>
                  {(tplOfSv?.questions || []).map((q: any, i: number) => (
                    <div key={q.id} style={{ marginTop: 8 }}>
                      <div className="field-label">{i + 1}. {q.text || 'Вопрос'} {q.req && <span className="req">*</span>}{q.attr !== '—' && <span> (в БДО: {sv.bdo[q.attr] || '—'})</span>}</div>
                      {q.type === 'Да / Нет' ? <Select style={{ width: '100%' }} disabled={!editable} value={answers[q.id] || undefined} options={['Да', 'Нет'].map((x) => ({ value: x, label: x }))} onChange={(v) => setAnswers({ ...answers, [q.id]: v })} />
                        : q.type === 'Фото' ? <Space>{editable && <FilePick label="Добавить фото" accept=".jpg,.jpeg,.png" entityType="survey" entityId={String(sv.id)} onUploaded={(f) => setAnswers({ ...answers, [q.id]: f.name })} />}<span className="mono">{answers[q.id] || '—'}</span></Space>
                          : <Input disabled={!editable} type={q.type === 'Дата' ? 'date' : 'text'} inputMode={q.type === 'Число' ? 'decimal' : undefined} value={answers[q.id] || ''} onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })} />}
                    </div>
                  ))}
                  {editable && <Space style={{ marginTop: 12, justifyContent: 'flex-end', width: '100%' }} wrap>
                    <Button onClick={async () => { try { await put(`/surveys/${sv.id}/answers`, { answers }); message.success('Ответы сохранены'); surveys.reload(); } catch (e) { showError(e); } }}>Сохранить ответы</Button>
                    <Button disabled={missing.length > 0} onClick={async () => { try { await put(`/surveys/${sv.id}/answers`, { answers }); await post(`/surveys/${sv.id}/complete`); message.success('Опрос заполнен и передан на проверку'); surveys.reload(); } catch (e) { showError(e); } }}>Завершить заполнение</Button>
                    <Button type="primary" style={{ background: sv.status === 'Заполнен' ? '#1E7B34' : undefined }} disabled={sv.status !== 'Заполнен'} onClick={async () => {
                      try { const r = await post(`/surveys/${sv.id}/accept`); message[r.discrepancies ? 'warning' : 'success'](r.discrepancies ? `Опрос принят. Создано запросов на расхождение с БДО: ${r.discrepancies}` : 'Опрос принят, расхождений с БДО нет'); surveys.reload(); } catch (e) { showError(e); }
                    }}>Принять</Button>
                  </Space>}
                  {editable && missing.length > 0 && <div className="hint">Не заполнены обязательные вопросы: {missing.length}</div>}
                </>;
              })()}
            </div>
          </div>
        </>
      )}
      {tab === 'Запросы на расхождения' && (
        <Table size="small" rowKey="id" loading={disc.loading} dataSource={disc.data || []} pagination={{ pageSize: 20 }} title={() => <span className="hint">Атрибуты из БДО в БДТС только для чтения: расхождения закрываются статусом «Всё введено» после внесения в БДО<Rule code="D-DISC-01" /></span>} columns={[
          { title: 'ID запроса', dataIndex: 'number', render: (v) => <b className="mono" style={{ color: '#1F5FAD' }}>{v}</b> }, { title: 'Единица оборудования', render: (_: any, r: any) => <Link to={`/eo/${r.eoId}`}>{r.eo}</Link> },
          { title: 'Атрибут', dataIndex: 'attr' }, { title: 'Значение в БДО', dataIndex: 'bdo', render: (v) => <span className="mono hint">{v}</span> }, { title: 'Значение по опросу', dataIndex: 'fact', render: (v) => <b className="mono">{v}</b> },
          { title: 'Контрольный срок', dataIndex: 'due', render: (v, r: any) => <span style={{ color: r.status !== 'Всё введено' && v < app.me!.today ? '#B42318' : undefined }}>{fmtDate(v)}</span> },
          { title: 'Статус', render: (_: any, r: any) => <StatusChip status={r.status !== 'Всё введено' && r.due < app.me!.today ? 'Просрочен' : r.status} compact /> },
          ...(can ? [{ title: '', render: (_: any, r: any) => r.status !== 'Всё введено' && <a onClick={async () => { await post(`/discrepancies/${r.id}/close`); message.success('Запрос закрыт: «Всё введено»'); disc.reload(); }}>Закрыть: «Всё введено»</a> }] : [])]} />
      )}
    </div>
  );
});

export default Surveys;
