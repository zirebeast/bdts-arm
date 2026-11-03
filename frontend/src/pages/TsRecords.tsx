// W-3.4 Реестр записей о техническом состоянии + создание записи (КР/ТОиР) + внешние операции «Импорт данных» / «Загрузка начальных данных» (R-IMP-01)
import { DownOutlined, DownloadOutlined, InboxOutlined, PlusOutlined } from '@ant-design/icons';
import { AutoComplete, Button, DatePicker, Dropdown, Input, Modal, Select, Space, Table, Upload, message } from 'antd';
import { observer } from 'mobx-react-lite';
import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { download, get, post, upload } from '../api';
import { useLoad } from '../hooks';
import { app } from '../store';
import { ReadOnlyBanner, Rule, ScreenTitle, StatusChip, fieldErrors, fmtDate, showError } from '../ui';

const TsRecords = observer(() => {
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const [f, setF] = useState({ q: sp.get('q') || '', confirm: sp.get('confirm') || '', rtype: '' });
  const [page, setPage] = useState(1);
  const { data, loading, reload } = useLoad(() => get('/ts-records', { ...f, page, size: 20 }), [f, page]);
  const [create, setCreate] = useState<any>(null);
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [eoOpts, setEoOpts] = useState<any[]>([]);
  const [imp, setImp] = useState<{ kind: string; file?: File; res?: any } | null>(null);
  const [busy, setBusy] = useState(false);

  const cols: any[] = [
    { title: '1. Ключевые идентификаторы', children: [
      { title: 'ID записи', dataIndex: 'number', width: 150, fixed: 'left', render: (v: string) => <b className="mono" style={{ color: '#1F5FAD' }}>{v}</b> },
      { title: 'Тип записи о тех. состоянии', dataIndex: 'recordType', width: 200 },
      { title: 'Техническое место', dataIndex: 'tmCode', width: 230, render: (v: string) => <span className="mono">{v}</span> },
      { title: 'Единица оборудования', dataIndex: 'eoName', width: 220 }] },
    { title: '2. Данные тех. состояния', children: [
      { title: 'Дата регистрации ТС', dataIndex: 'regDate', width: 120, render: fmtDate },
      { title: 'Актуальный статус объекта', dataIndex: 'st', width: 170 },
      { title: 'Краткое описание', dataIndex: 'desc', width: 240, ellipsis: true },
      { title: 'Статус подтверждения', dataIndex: 'confirm', width: 235, render: (s: string) => <StatusChip status={s} compact /> },
      { title: 'Дата статуса', dataIndex: 'statusDate', width: 110, render: fmtDate }] },
    { title: 'Системные поля', children: [
      { title: 'Дата создания', dataIndex: 'createdAt', width: 110, render: fmtDate }, { title: 'Дата обновления', dataIndex: 'updatedAt', width: 110, render: fmtDate },
      { title: 'Статус записи', dataIndex: 'recordStatus', width: 110 }, { title: 'Примечания', dataIndex: 'notes', width: 200, ellipsis: true, render: (v: string) => v || 'Нет' }] },
  ];

  const runImport = async () => {
    if (!imp?.file) return;
    setBusy(true);
    try {
      const r = await upload('/ts-import', { file: imp.file }, { kind: imp.kind });
      setImp({ ...imp, res: r });
      if (r.state === 'done') { message[r.warnings ? 'warning' : 'success'](r.description); reload(); } else message.info('Операция поставлена в очередь; ход выполнения — в логе загрузки данных');
    } catch (e) { showError(e); } finally { setBusy(false); }
  };

  return (
    <div>
      <ScreenTitle code="W-3.4" title="Реестр записей о техническом состоянии" extra={<>
        {app.can('ts.create') && <Button type="primary" icon={<PlusOutlined />} onClick={() => { setErrs({}); setCreate({ recordType: 'Выполнение ТОиР', eoId: null, eoName: '', st: 'Работоспособное', desc: '', notes: '', regDate: '' }); get('/refs/eo').then(setEoOpts); }}>Создать запись</Button>}
        {app.can('ts.import') && <Dropdown menu={{ items: ['Импорт данных', 'Загрузка начальных данных'].map((k) => ({ key: k, label: k })), onClick: (e) => setImp({ kind: e.key }) }}><Button>Внешние операции <DownOutlined /></Button></Dropdown>}
        <Button icon={<DownloadOutlined />} onClick={() => download('/ts-records/export.xlsx', f)}>Сохранить в Excel</Button>
        <Link to="/logs"><Button>Лог</Button></Link>
      </>} />
      <ReadOnlyBanner screen="W-3.4" />
      <div className="toolbar">
        <Space wrap>
          <Select style={{ width: 230 }} value={f.confirm} onChange={(v) => { setF({ ...f, confirm: v }); setPage(1); }} options={[{ value: '', label: 'Все статусы подтверждения' }, { value: 'Подтверждено', label: 'Подтверждено' }, { value: 'Требует подтверждения', label: 'Требует подтверждения' }]} />
          <Select style={{ width: 250 }} value={f.rtype} onChange={(v) => { setF({ ...f, rtype: v }); setPage(1); }} options={[{ value: '', label: 'Все типы записей' }, ...['Диагностическое обследование', 'Выполнение ТОиР', 'Выполнение КР'].map((x) => ({ value: x, label: x }))]} />
        </Space>
        <Input.Search allowClear defaultValue={f.q} placeholder="ID записи, ЕО, описание" style={{ width: 300 }} onSearch={(v) => { setF({ ...f, q: v }); setPage(1); }} />
      </div>
      <Table size="small" bordered rowKey="id" loading={loading} columns={cols} dataSource={data?.items || []} scroll={{ x: 2150 }}
        pagination={{ current: page, pageSize: 20, total: data?.total || 0, onChange: setPage, showTotal: (t) => `Всего: ${t}` }} onRow={(r) => ({ onClick: () => nav(`/ts-records/${r.id}`), className: 'clickable-row' })} />

      <Modal open={!!create} title="Создание записи о техническом состоянии" okText="Сохранить" cancelText="Отмена" confirmLoading={busy} onCancel={() => setCreate(null)}
        onOk={async () => {
          setBusy(true);
          try { const r = await post('/ts-records', create); message.success(`Запись ${r.number} создана и требует подтверждения`); setCreate(null); reload(); } catch (e) { setErrs(fieldErrors(e)); showError(e); } finally { setBusy(false); }
        }}>
        {create && <Space direction="vertical" style={{ width: '100%' }}>
          <div className="hint">Запись по результатам КР и ТОиР вводится вручную; записи по результатам ДО создаются автоматически.</div>
          <div><div className="field-label">Тип записи о тех. состоянии <span className="req">*</span></div><Select style={{ width: '100%' }} value={create.recordType} onChange={(v) => setCreate({ ...create, recordType: v })} options={['Выполнение ТОиР', 'Выполнение КР'].map((x) => ({ value: x, label: x }))} /></div>
          <div><div className="field-label">Единица оборудования <span className="req">*</span></div>
            <AutoComplete style={{ width: '100%' }} value={create.eoName} status={errs.eoId ? 'error' : undefined} placeholder="Поиск по наименованию или коду"
              options={eoOpts.map((e) => ({ value: `${e.code} · ${e.name}`, eo: e }))} onSearch={async (q) => setEoOpts(await get('/refs/eo', { q }))}
              onChange={(v) => setCreate({ ...create, eoName: v, eoId: null })} onSelect={(_, o: any) => setCreate({ ...create, eoName: `${o.eo.code} · ${o.eo.name}`, eoId: o.eo.id })} />
            {errs.eoId && <div className="err">{errs.eoId}</div>}</div>
          <div><div className="field-label">Актуальный статус объекта <span className="req">*</span></div><Select style={{ width: '100%' }} value={create.st} onChange={(v) => setCreate({ ...create, st: v })} options={['Исправное', 'Работоспособное', 'Ограниченно работоспособное', 'Неработоспособное', 'В эксплуатации'].map((x) => ({ value: x, label: x }))} /></div>
          <div><div className="field-label">Дата регистрации технического состояния</div><DatePicker format="DD.MM.YYYY" onChange={(d) => setCreate({ ...create, regDate: d ? d.format('YYYY-MM-DD') : '' })} /></div>
          <div><div className="field-label">Краткое описание технического состояния объекта</div><Input value={create.desc} onChange={(e) => setCreate({ ...create, desc: e.target.value })} /></div>
          <div><div className="field-label">Примечания</div><Input value={create.notes} onChange={(e) => setCreate({ ...create, notes: e.target.value })} /></div>
        </Space>}
      </Modal>

      <Modal open={!!imp} title={`Внешняя операция «${imp?.kind}»`} onCancel={() => setImp(null)} destroyOnClose
        footer={imp?.res ? <><Button onClick={() => setImp(null)}>Закрыть</Button><Button type="primary" onClick={() => nav(`/logs?log=${imp.res.id}`)}>Открыть лог</Button></>
          : <><Button onClick={() => setImp(null)}>Отмена</Button><Button type="primary" disabled={!imp?.file} loading={busy} onClick={runImport}>Выполнить</Button></>}>
        {imp && <Space direction="vertical" style={{ width: '100%' }}>
          <div className="hint">Файл .xlsx, листы в порядке: «Запись о техсостоянии», «Документы измерения», «Сообщения (дефекты)», «Мероприятия КР и ТОиР», «Отчёт ДО»<Rule code="R-IMP-01" />.</div>
          <div className="hint">{imp.kind === 'Загрузка начальных данных' ? 'Загружаются данные о ДО прошлых периодов, включая лист «Отчёт ДО». Ход загрузки пишется в лог.' : 'Лист «Отчёт ДО» пользователем не загружается.'}</div>
          <a onClick={() => download('/ts-records/import-template.xlsx')}><DownloadOutlined /> Скачать шаблон файла</a>
          <Upload.Dragger accept=".xlsx" maxCount={1} beforeUpload={(file) => { setImp({ ...imp, file, res: undefined }); return false; }} onRemove={() => setImp({ ...imp, file: undefined })}>
            <p className="ant-upload-drag-icon"><InboxOutlined /></p><p>Выберите файл .xlsx</p>
          </Upload.Dragger>
          {imp.res && <div className={imp.res.warnings ? 'banner-warn' : imp.res.state === 'error' ? 'banner-err' : 'banner-ok'}>{imp.res.description}. Подробности — в логе загрузки данных.</div>}
        </Space>}
      </Modal>
    </div>
  );
});

export default TsRecords;
