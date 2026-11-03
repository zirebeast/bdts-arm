// W-3.5 Запись о техническом состоянии (6 вкладок): поля «требует подтверждения» (R-B316-02), подтверждение (R-B316-01), файлы (R-FILE-01)
import { DeleteOutlined, DownloadOutlined, PlusOutlined, UploadOutlined } from '@ant-design/icons';
import { Button, DatePicker, Input, Modal, Select, Space, Table, Tabs, Tag, Upload, message } from 'antd';
import { observer } from 'mobx-react-lite';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { del, download, get, patch, post, upload } from '../api';
import LoadState from '../components/LoadState';
import { useLoad } from '../hooks';
import { app } from '../store';
import { BackLink, Block, KV, Rule, ScreenTitle, StatusChip, fmtDate, fmtDateTime, fmtNum, showError } from '../ui';

const Flag = () => <Tag color="orange" style={{ fontSize: 10, marginLeft: 4 }}>требует подтверждения</Tag>;

const TsRecordCard = observer(() => {
  const { id } = useParams();
  const { data: r, setData, loading, error, reload } = useLoad(() => get(`/ts-records/${id}`), [id]);
  const [measure, setMeasure] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const editable = app.can('ts.edit');
  const doPatch = async (fn: () => Promise<any>, msg: string) => {
    try { setData(await fn()); message.warning(msg); } catch (e) { showError(e); }
  };
  return (
    <LoadState loading={loading} error={error} reload={reload}>{() => {
      const flagMsg = 'Изменено поле, требующее подтверждения: запись переведена в «Требует подтверждения»';
      const rec = (
        <>
          <Block title="1. Ключевые идентификаторы"><KV items={[['ID записи', <span className="mono">{r.number}</span>], ['Тип записи о тех. состоянии', r.recordType],
            ['Техническое место', r.tmId ? <Link className="mono" to={`/tm/${r.tmId}`}>{r.tmCode}</Link> : '—'], ['Единица оборудования', r.eoId ? <Link to={`/eo/${r.eoId}`}>{r.eoName}</Link> : '—']]} /></Block>
          <Block title="2. Атрибуты даты и времени"><KV items={[['Дата регистрации технического состояния', fmtDate(r.regDate)], ['Дата следующего осмотра / ТО', fmtDate(r.next)]]} /></Block>
          <Block title="3. Информация о техническом состоянии">
            <KV items={[['Актуальный статус объекта', <span><Select style={{ width: 260 }} disabled={!editable} value={r.st || undefined}
              options={['Исправное', 'Работоспособное', 'Ограниченно работоспособное', 'Неработоспособное', 'В эксплуатации'].map((x) => ({ value: x, label: x }))}
              onChange={(v) => doPatch(() => patch(`/ts-records/${r.id}`, { st: v }), flagMsg)} /><Flag /><Rule code="R-B316-02" /></span>],
              ['Краткое описание технического состояния объекта', r.desc], ['Оценка износа, %', fmtNum(r.wear)], ['Остаточный ресурс, лет', fmtNum(r.life, 1)]]} />
          </Block>
          <Block title="4. Подтверждение данных">
            <KV items={[['ФИО сотрудника', r.confirmedBy || '—'], ['Должность сотрудника', r.confirmedByPosition || '—'], ['Дата статуса', fmtDate(r.statusDate)],
              ['Статус подтверждения данных о техническом состоянии', <span><Select style={{ width: 230 }} value={r.confirm} disabled={!app.can('ts.confirm')}
                options={['Подтверждено', 'Требует подтверждения'].map((x) => ({ value: x, label: x }))}
                onChange={async (v) => { try { setData(await post(`/ts-records/${r.id}/confirm`, { status: v })); message.success('Статус подтверждения сохранён'); } catch (e) { showError(e); } }} /><Rule code="R-B316-01" /></span>]]} />
          </Block>
          <Block title="5. Системные поля"><KV cols={4} items={[['Дата создания записи', fmtDate(r.createdAt)], ['Дата последнего обновления', fmtDate(r.updatedAt)], ['Статус записи', r.recordStatus], ['Примечания', r.notes || 'Нет']]} /></Block>
        </>
      );
      const tabs = [
        { key: 'rec', label: 'Запись о техническом состоянии', children: rec },
        { key: 'meas', label: `Документы измерения (${r.measurements.length})`, children: <Table size="small" rowKey="id" pagination={false} dataSource={r.measurements} scroll={{ x: 1300 }} columns={[
          { title: 'Ссылка на запись', render: () => <span className="mono">{r.number}</span> }, { title: 'ID документа измерения', dataIndex: 'id' }, { title: 'Точка контроля', dataIndex: 'point' },
          { title: 'Числовое значение', dataIndex: 'value', render: (v) => <span className="mono">{fmtNum(v)}</span> }, { title: 'Ед. изм.', dataIndex: 'unit' }, { title: 'Текстовое значение', dataIndex: 'text', render: (v) => v || '—' },
          { title: 'Номер позиции', dataIndex: 'position' }, { title: 'Область / Место', dataIndex: 'area' }, { title: 'Дата и время регистрации', dataIndex: 'at', render: fmtDateTime },
          { title: 'Инструмент', dataIndex: 'instrument' }, { title: 'Эксперт ДО', dataIndex: 'expert' }, { title: 'Метод контроля', dataIndex: 'method' }]} /> },
        { key: 'msg', label: `Сообщения ТОиР (${r.messages.length})`, children: <Table size="small" rowKey="id" pagination={false} dataSource={r.messages} scroll={{ x: 1300 }} columns={[
          { title: 'ID сообщения', dataIndex: 'id' }, { title: 'Номер в журнале дефектов', dataIndex: 'journalNo' }, { title: 'Дата записи', dataIndex: 'journalDate', render: fmtDate },
          { title: 'Автор', dataIndex: 'author' }, { title: 'Вид сообщения', dataIndex: 'kind' }, { title: 'Описание дефекта', dataIndex: 'description' }, { title: 'Код дефекта', dataIndex: 'code', render: (v) => <span className="mono">{v}</span> },
          { title: 'Критичность', dataIndex: 'criticality' },
          { title: 'Статус устранения', render: (_: any, m: any) => <span><Select size="small" style={{ width: 130 }} disabled={!editable} value={m.fixStatus} options={['Не устранен', 'Устранен'].map((x) => ({ value: x, label: x }))}
            onChange={(v) => doPatch(() => patch(`/ts-records/${r.id}/messages/${m.id}`, { fixStatus: v }), flagMsg)} /><Flag /></span> },
          { title: 'Документ измерения', dataIndex: 'measurementId', render: (v) => v || '—' }]} /> },
        { key: 'rep', label: 'Отчёт о диагностическом обследовании', children: Object.keys(r.doReport || {}).length ? <KV cols={3} items={[
          ['ID строки ПП', r.doReport.pp], ['Номер Заказа', r.doReport.order], ['Название Заказа', r.doReport.orderName], ['Исполнитель', r.doReport.executor], ['Вид ДО', r.doReport.vid],
          ['Начало работ. План', r.doReport.planStart], ['Начало работ. Факт', r.doReport.factStart], ['Окончание работ. План', r.doReport.planEnd], ['Окончание работ. Факт', r.doReport.factEnd],
          ['Номер Технического отчета', r.report ? <Link to={`/reports/${r.report.id}`} className="mono">{r.report.number}</Link> : r.doReport.toNumber], ['Дата Технического отчета', r.doReport.toDate],
          ['Дата согласования ТО ГД', r.doReport.gdDate], ['Дата: ТО принят ДЭО', r.doReport.deoDate], ['Дата ЭПБ', r.doReport.epbDate], ['Выполненные операции', r.doReport.ops], ['Стоимость по трудозатратам', r.doReport.cost]]} />
          : <div className="hint">Отчёт о ДО отсутствует (запись не по результатам ДО).</div> },
        { key: 'act', label: `Мероприятия КР и ТОиР (${r.measures.length})`, children: <>
          {editable && <div style={{ textAlign: 'right', marginBottom: 8 }}><Button type="primary" icon={<PlusOutlined />} onClick={() => setMeasure({ name: '', kind: 'Текущий ремонт', executor: 'ОРГ_10', planEnd: '' })}>Добавить мероприятие</Button></div>}
          <Table size="small" rowKey="id" pagination={false} dataSource={r.measures} scroll={{ x: 1500 }} columns={[
            { title: 'ID строки ПП', dataIndex: 'pp' }, { title: 'Номер Заказа', dataIndex: 'order' }, { title: 'Название Заказа', dataIndex: 'name' }, { title: 'Вид ремонта', dataIndex: 'kind' },
            { title: 'Исполнитель', dataIndex: 'executor' }, { title: 'Начало. План', dataIndex: 'planStart', render: fmtDate }, { title: 'Окончание. План', dataIndex: 'planEnd', render: fmtDate },
            { title: 'Окончание. Факт', dataIndex: 'factEnd', render: fmtDate }, { title: '№ исполнительной документации', dataIndex: 'docNo' }, { title: 'Номер исправленного дефекта', dataIndex: 'defectNo' },
            { title: 'Выполненные операции', dataIndex: 'ops' }, { title: 'Причины невыполнения', dataIndex: 'reason' }]} />
        </> },
        { key: 'files', label: `Файлы (${r.files.length})`, children: <>
          {editable && <Upload.Dragger style={{ marginBottom: 8 }} showUploadList={false} multiple
            customRequest={async ({ file, onSuccess, onError }) => { try { setData(await upload(`/ts-records/${r.id}/files`, { file: file as File })); message.success('Файл загружен'); onSuccess?.({}); } catch (err) { showError(err); onError?.(err as any); } }}>
            <p><UploadOutlined /> Перетащите файлы сюда или нажмите для выбора (хранилище S3)</p>
          </Upload.Dragger>}
          <Table size="small" rowKey="id" pagination={false} dataSource={r.files} locale={{ emptyText: 'Файлов нет' }} columns={[
            { title: 'Имя файла', dataIndex: 'name', render: (v) => <span className="mono">{v}</span> }, { title: 'Тип', dataIndex: 'mime' }, { title: 'Дата загрузки', dataIndex: 'at', render: fmtDateTime },
            { title: 'Пользователь, загрузивший файл', dataIndex: 'by' }, { title: 'Размер', dataIndex: 'size', render: (v) => `${fmtNum(v / 1024, 1)} КБ` },
            { title: '', render: (_: any, fl: any) => <Space><a onClick={() => download(`/files/${fl.id}`)}><DownloadOutlined /> Выгрузить файл</a>
              {editable && <a style={{ color: '#B42318' }} onClick={() => Modal.confirm({ title: 'Удалить файл?', content: `Файл ${fl.name} будет удалён из записи.`, okText: 'Удалить файл', okButtonProps: { danger: true }, cancelText: 'Отмена',
                onOk: async () => { await del(`/files/${fl.id}`); reload(); message.warning(`Файл ${fl.name} удалён`); } })}><DeleteOutlined /> Удалить</a>}</Space> }]} />
        </> },
      ];
      return (
        <div>
          <ScreenTitle code="W-3.5" back={<BackLink to="/ts-records">К реестру записей</BackLink>} title={<Space wrap>Запись о техническом состоянии № {r.number}<StatusChip status={r.confirm} /></Space>}
            sub={<>{r.report && <>Родительский ТО: <Link className="mono" to={`/reports/${r.report.id}`}>{r.report.number}</Link> · </>}{r.resultId && <>По результату ДО · </>}Источник: {({ manual: 'ввод вручную', result: 'результат ДО', report: 'ТО ГД', import: 'импорт xlsx' } as any)[r.source] || r.source}</>} />
          <div className="panel"><Tabs items={tabs} /></div>
          <Modal open={!!measure} title="Добавление мероприятия КР и ТОиР" okText="Сохранить" cancelText="Отмена" confirmLoading={busy} onCancel={() => setMeasure(null)}
            onOk={async () => {
              if (!measure.name.trim()) { message.error('Заполните «Название Заказа»'); return; }
              setBusy(true);
              try { setData(await post(`/ts-records/${r.id}/measures`, measure)); setMeasure(null); message.warning(flagMsg); } catch (e) { showError(e); } finally { setBusy(false); }
            }}>
            {measure && <Space direction="vertical" style={{ width: '100%' }}>
              <div><div className="field-label">Название Заказа <span className="req">*</span></div><Input value={measure.name} onChange={(e) => setMeasure({ ...measure, name: e.target.value })} /></div>
              <div><div className="field-label">Вид ремонта <span className="req">*</span></div><Select style={{ width: '100%' }} value={measure.kind} onChange={(v) => setMeasure({ ...measure, kind: v })} options={['Текущий ремонт', 'Капитальный ремонт', 'Техническое обслуживание'].map((x) => ({ value: x, label: x }))} /></div>
              <div><div className="field-label">Исполнитель <span className="req">*</span></div><Select style={{ width: '100%' }} value={measure.executor} onChange={(v) => setMeasure({ ...measure, executor: v })} options={(app.refs?.orgs || []).map((o) => ({ value: o.code, label: `${o.code} — ${o.name}` }))} /></div>
              <div><div className="field-label">Дата окончания выполнения работ. План <span className="req">*</span></div><DatePicker format="DD.MM.YYYY" onChange={(d) => setMeasure({ ...measure, planEnd: d ? d.format('YYYY-MM-DD') : '' })} /></div>
            </Space>}
          </Modal>
        </div>
      );
    }}</LoadState>
  );
});

export default TsRecordCard;
