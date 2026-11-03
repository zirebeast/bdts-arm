// W-8.3 (Δ) Сводка объекта X/Y/Z: организации, бригада (специалисты НК), ЕО из МП-3 «БДО», создание и копирование ЕО (V-EQ-033), задачи ПС-0
import { CopyOutlined, DatabaseOutlined, PlusOutlined } from '@ant-design/icons';
import { Button, Checkbox, Collapse, Input, Modal, Select, Space, Table, Tag, message } from 'antd';
import { observer } from 'mobx-react-lite';
import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { get, post } from '../api';
import FlowBar from '../components/FlowBar';
import LoadState from '../components/LoadState';
import { useLoad } from '../hooks';
import { app } from '../store';
import { BackLink, Block, KV, Rule, ScreenTitle, StatusChip, TolBadge, fieldErrors, fmtDate, showError } from '../ui';

const EMPTY = { type: '', mark: '', techNum: '', serialNum: '', year: '', manufacturer: '', dn: '', pn: '', sCalc: '', steelGrade: '', matCover: '', matSpindle: '', matSeal: '' };
const VID_BY_TYPE: Record<string, string> = { 'ГРС': 'grs', 'КС': 'tpa', 'УКПГ': 'wellhead' };

const ObjectCard = observer(() => {
  const { id } = useParams();
  const nav = useNavigate();
  const { data: o, loading, error, reload } = useLoad(() => get(`/inbound/objects/${id}`), [id]);
  const [bdo, setBdo] = useState<any[] | null>(null);
  const [sel, setSel] = useState<string[]>([]);
  const [eo, setEo] = useState<{ mode: 'create' | 'copy'; src?: any; form: any } | null>(null);
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [q, setQ] = useState('');
  const can = app.can('int.load');
  const today = app.me!.today;
  const saveEo = async (goControl: boolean) => {
    try {
      const r = await post(`/inbound/objects/${id}/eo`, { form: eo!.form, copiedFrom: eo!.mode === 'copy' ? eo!.src.techNum : '' });
      message.success(eo!.mode === 'copy' ? `Создана копия ЕО: тех. № ${eo!.form.techNum}. Замеры, фото и дефекты не скопированы` : `ЕО создана: тех. № ${eo!.form.techNum} (${r.code})`);
      setEo(null);
      if (goControl) nav(o.taskId ? `/results/${o.taskId}` : `/tasks?create=1&vid=${VID_BY_TYPE[o.type] || 'tpa'}&xyz=${encodeURIComponent(o.cipher)}&loc=${encodeURIComponent(o.name)}&deo=${o.deo}`);
      else reload();
    } catch (e) { setErrs(fieldErrors(e)); showError(e); }
  };
  return (
    <LoadState loading={loading} error={error} reload={reload}>{() => {
      const list = o.eos.filter((e: any) => !q || [e.type, e.mark, e.techNum, e.serialNum].some((x: string) => String(x).toLowerCase().includes(q.toLowerCase())));
      const pending = o.eos.filter((e: any) => e.sync === 'pending');
      const F = (k: string, label: string, req = true, opts?: string[]) => (
        <div key={k}><div className="field-label">{label} {req && <span className="req">*</span>}</div>
          {opts ? <Select style={{ width: '100%' }} value={eo!.form[k] || undefined} placeholder="Выберите…" status={errs[k] ? 'error' : undefined} onChange={(v) => setEo({ ...eo!, form: { ...eo!.form, [k]: v } })} options={opts.map((x) => ({ value: x, label: x }))} />
            : <Input autoFocus={eo!.mode === 'copy' && k === 'techNum'} value={eo!.form[k]} status={errs[k] ? 'error' : undefined} onChange={(e) => setEo({ ...eo!, form: { ...eo!.form, [k]: e.target.value } })}
              style={eo!.mode === 'copy' && (k === 'techNum' || k === 'serialNum') ? { boxShadow: '0 0 0 2px rgba(31,95,173,.3)' } : undefined} />}
          {errs[k] && <div className="err">{errs[k]}</div>}</div>
      );
      return (
        <div>
          <FlowBar />
          <ScreenTitle code="W-8.3" back={<BackLink to="/inbound/objects">К объектам</BackLink>} title={<Space wrap>Сводка задания · <span className="mono">{o.cipher}</span><StatusChip status={o.status} />{o.local && <Tag color="orange">Локальное</Tag>}</Space>}
            extra={o.taskId ? <Button type="primary" onClick={() => nav(`/results/${o.taskId}`)}>Перейти в «Контроль» (результат ДО) →</Button>
              : app.can('task.create') && <Button type="primary" disabled={!o.eos.length} onClick={() => nav(`/tasks?create=1&vid=${VID_BY_TYPE[o.type] || 'tpa'}&xyz=${encodeURIComponent(o.cipher)}&loc=${encodeURIComponent(o.name)}&deo=${o.deo}`)}>Создать задание на ДО по объекту →</Button>} />
          <Block title="Метаданные объекта"><KV cols={4} items={[['Наименование ОПО', o.name], ['Тип сооружения', o.type], ['Рег. / инв. №', o.reg], ['Класс опасности', o.hazard], ['Адрес', o.address],
            ['Дата обследования', fmtDate(o.date)], ['Тип задания', o.local ? 'Внеплановое обследование' : `${o.vid} · ${o.ppRow}`], ['Источник', o.local ? 'Создан вручную (isLocal)' : o.source]]} /></Block>
          <div className="grid g2">
            <Block title="Организации"><KV cols={2} items={[['Заказчик', o.customer || '—'], ['Эксплуатирующая организация', o.deo], ['Организация-исполнитель', o.executor], ['ЛНК', o.lnk || '—']]} /></Block>
            <Block title={`Состав бригады (специалисты НК) · ${o.brigade.name}`}>
              {o.brigade.members.map((b: any) => {
                const exp = b.validUntil < today;
                return <div key={b.cert} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', borderBottom: '1px dashed #EEF1F4', padding: '4px 0' }}>
                  <b>{b.fio}, {b.level} уровень</b><span className="mono hint">{b.cert}</span>{b.methods.map((m: string) => <Tag key={m}>{m}</Tag>)}
                  <span style={{ marginLeft: 'auto' }}>{exp ? <TolBadge t="exceeded" /> : null} <span className={exp ? '' : 'hint'} style={exp ? { color: '#C62828', fontWeight: 600 } : undefined}>{exp ? `Просрочено ${fmtDate(b.validUntil)}` : `до ${fmtDate(b.validUntil)}`}</span></span></div>;
              })}
              <div className="hint">Специалист с просроченным удостоверением не назначается на методы.</div>
            </Block>
          </div>
          <div className="toolbar">
            <Space wrap><b>Единицы оборудования объекта ({o.eos.length})</b><Input.Search allowClear placeholder="Тех. №, зав. №, марка" style={{ width: 240 }} onSearch={setQ} /></Space>
            {can && <Space>
              <Button icon={<DatabaseOutlined />} onClick={async () => { try { const r = await get(`/inbound/objects/${id}/bdo`); setBdo(r); setSel(r.filter((x: any) => !x.already).map((x: any) => x.asupp)); } catch (e) { showError(e); } }}>Загрузить ЕО из БДО</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => { setErrs({}); setEo({ mode: 'create', form: { ...EMPTY } }); }}>Добавить ЕО</Button></Space>}
          </div>
          {pending.length > 0 && <div className="banner-warn" style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <span>{pending.length} ЕО создано вне БДО (origin = field_created, sync = pending)<Rule code="V-EQ-033" />. Их нужно добавить в МП-3 «БДО».</span>
            {can && <Button size="small" onClick={async () => { const r = await post(`/inbound/objects/${id}/ps0`); message.info(r.created ? `Созданы задачи ПС-0 на добавление ЕО/ТМ в БДО: ${r.created}` : 'Задачи уже созданы'); reload(); }}>Создать задачи ПС-0 на добавление в БДО</Button>}</div>}
          <Table size="small" rowKey="id" pagination={false} dataSource={list} scroll={{ x: 1100 }} locale={{ emptyText: o.eos.length ? 'Нет ЕО по запросу' : 'ЕО ещё не загружены. Загрузите ЕО из БДО по техническим местам объекта или добавьте ЕО вручную.' }} columns={[
            { title: 'Тип оборудования ↑', dataIndex: 'type' }, { title: 'Марка', dataIndex: 'mark' }, { title: 'Тех. №', dataIndex: 'techNum', render: (v) => <span className="mono">{v}</span> },
            { title: 'Зав. № ↑', dataIndex: 'serialNum', render: (v) => <span className="mono">{v}</span> }, { title: 'DN / PN', render: (_: any, e: any) => <span className="mono">{e.dn} / {e.pn}</span> },
            { title: 's расч., мм', dataIndex: 'sCalc', render: (v) => <span className="mono">{v || '—'}</span> },
            { title: 'Источник', render: (_: any, e: any) => (e.origin === 'asupp' ? <span>БДО <span className="mono">{e.code}</span></span> : e.copiedFrom ? `Копия ЕО ${e.copiedFrom}` : 'Создана вручную') },
            { title: 'БДО', render: (_: any, e: any) => <div><StatusChip status={e.sync === 'synced' ? 'Синхронизирована' : e.sync === 'conflict' ? 'Конфликт с БДО' : 'Ожидает добавления в БДО'} compact />
              {e.conflict && <div className="err">{e.conflict}</div>}{e.task && <div className="hint">{e.task}</div>}</div> },
            { title: '', render: (_: any, e: any) => <Space>{can && <Button size="small" icon={<CopyOutlined />} onClick={() => { setErrs({}); setEo({ mode: 'copy', src: e, form: { ...EMPTY, ...e, techNum: '', serialNum: '' } }); }}>Копировать ЕО</Button>}
              <Link to={`/eo/${e.id}`}>Карточка ЕО →</Link></Space> }]} />
          <div className="hint" style={{ marginTop: 6 }}>Сортировка: тип оборудования А→Я, затем заводской № по числовому значению.</div>

          <Modal open={!!bdo} width={900} title="Загрузка ЕО из МП-3 «БДО» (ФМ-3.2)" okText={`Добавить выбранные (${sel.length})`} cancelText="Отмена" okButtonProps={{ disabled: !sel.length }} onCancel={() => setBdo(null)}
            onOk={async () => { try { const r = await post(`/inbound/objects/${id}/bdo`, { asupp: sel }); message.success(`Загружено ЕО из БДО: ${r.added}`); setBdo(null); reload(); } catch (e) { showError(e); } }}>
            <p className="hint">Запрос по ТМ объекта <span className="mono">{o.tm || o.cipher}</span>. Найдено {bdo?.length} ЕО. Атрибуты из БДО редактируются только через опросные листы и запросы на расхождение (W-3.8).</p>
            <Table size="small" rowKey="asupp" pagination={false} dataSource={bdo || []} columns={[
              { title: '', width: 40, render: (_: any, b: any) => <Checkbox disabled={b.already} checked={sel.includes(b.asupp)} onChange={(e) => setSel(e.target.checked ? [...sel, b.asupp] : sel.filter((x) => x !== b.asupp))} /> },
              { title: 'ID ЕО (БДО)', dataIndex: 'asupp', render: (v) => <span className="mono">{v}</span> }, { title: 'Тип', dataIndex: 'type' }, { title: 'Марка', dataIndex: 'mark' },
              { title: 'Тех. №', dataIndex: 'techNum' }, { title: 'Зав. №', dataIndex: 'serialNum' }, { title: 's расч.', dataIndex: 'sCalc', render: (v) => v || '—' },
              { title: 'Проверка', render: (_: any, b: any) => (b.already ? 'Уже на объекте' : b.conflict ? <span style={{ color: '#B54708' }}>▲ {b.conflict}</span> : <span style={{ color: '#2E7D32' }}>● Готово</span>) }]} />
          </Modal>

          <Modal open={!!eo} width={880} title={eo?.mode === 'copy' ? `Копирование единицы оборудования (образец: тех. № ${eo.src.techNum})` : 'Создание единицы оборудования'} onCancel={() => setEo(null)}
            footer={<><Button onClick={() => setEo(null)}>Отмена</Button><Button onClick={() => saveEo(false)}>{eo?.mode === 'copy' ? 'Создать копию ЕО' : 'Сохранить ЕО'}</Button><Button type="primary" onClick={() => saveEo(true)}>Сохранить и перейти к контролю →</Button></>}>
            {eo && <>
              {eo.mode === 'copy' && <div className="banner-info">Паспортные поля и материалы скопированы. <b>Технологический № и заводской № очищены</b> — введите значения новой ЕО.</div>}
              <div className="field-label" style={{ textTransform: 'uppercase' }}>Идентификация</div>
              <div className="grid g4" style={{ marginBottom: 10 }}>{F('type', 'Тип оборудования', true, o.refs.tpaTypes)}{F('mark', 'Марка / обозначение')}{F('techNum', 'Технологический №')}{F('serialNum', 'Заводской №')}</div>
              <div className="field-label" style={{ textTransform: 'uppercase' }}>Паспортные параметры</div>
              <div className="grid g4" style={{ marginBottom: 10 }}>{F('year', 'Год изготовления', false)}{F('manufacturer', 'Изготовитель', false)}{F('dn', 'DN, мм', true, o.refs.dn.map(String))}{F('pn', 'PN, МПа')}{F('sCalc', 's расч., мм')}{F('steelGrade', 'Марка стали (§38)', true, o.refs.steels)}</div>
              <div className="field-label" style={{ textTransform: 'uppercase' }}>Материалы деталей</div>
              <div className="grid g3">{F('matCover', 'Крышка / пробка', false)}{F('matSpindle', 'Шпиндель / шток', false)}{F('matSeal', 'Уплотнения', false)}</div>
              {eo.mode === 'copy' && <Collapse style={{ marginTop: 12 }} items={[{ key: 'm', label: 'Что копируется, а что нет', children: <Table size="small" pagination={false} rowKey={(r: any) => r[0]} showHeader={false} dataSource={[
                ['Тех. №, зав. №, id', 'Не копируются (очищены)', 'exceeded'], ['Паспорт: тип, марка, год, изготовитель, DN, PN, s расч., сталь, материалы', 'Копируются полностью', 'ok'],
                ['Замеры, оценки ВИК, результаты ФД, стыки УЗК, хим. состав', 'Не копируются', 'exceeded'], ['Фото, записи ведомости дефектов', 'Не копируются', 'exceeded']]}
                columns={[{ dataIndex: 0 }, { dataIndex: 1, render: (v, r: any) => <span className={`tol tol-${r[2] === 'ok' ? 'ok' : 'ex'}`}>{v}</span> }]} /> }]} />}
              {Object.keys(errs).length > 0 && <div className="err" style={{ marginTop: 8 }}>Исправьте поля, отмеченные красным ({Object.keys(errs).length}).</div>}
            </>}
          </Modal>
        </div>
      );
    }}</LoadState>
  );
});

export default ObjectCard;
