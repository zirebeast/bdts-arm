// W-1.2 Карточка задания на ДО: просмотр, редактирование, отправка, согласование (R-B301-03…06), удаление, история
import { CheckCircleOutlined, CheckOutlined, DeleteOutlined, EditOutlined, ExportOutlined, HistoryOutlined, RightOutlined } from '@ant-design/icons';
import { Button, Modal, Space, message } from 'antd';
import { observer } from 'mobx-react-lite';
import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { del, get, post, put } from '../api';
import LoadState from '../components/LoadState';
import TaskForm, { TaskFormData, validateTask } from '../components/TaskForm';
import { useLoad } from '../hooks';
import { app } from '../store';
import { BackLink, Block, DecisionModal, HistoryModal, KV, Rule, ScreenTitle, StatusChip, fieldErrors, fmtDate, showError } from '../ui';

const TaskCard = observer(() => {
  const { id } = useParams();
  const nav = useNavigate();
  const { data: t, setData, loading, error, reload } = useLoad(() => get(`/tasks/${id}`), [id]);
  const [modal, setModal] = useState<'' | 'edit' | 'approve' | 'history'>('');
  const [draft, setDraft] = useState<TaskFormData | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const act = async (fn: () => Promise<any>, ok: string) => {
    setBusy(true);
    try { setData(await fn()); message.success(ok); app.loadNotes(); } catch (e: any) { showError(e); if (e.status === 409) reload(); } finally { setBusy(false); }
  };

  return (
    <LoadState loading={loading} error={error} reload={reload}>{() => (
      <div>
        <ScreenTitle code="W-1.2" back={<BackLink to={`/tasks?vid=${t.vid}`}>К списку заданий</BackLink>} title={<Space>Задание на ДО № {t.id}<StatusChip status={t.status} /></Space>} />
        <div className="toolbar">
          <Space wrap>
            <span className="field-label" style={{ margin: 0, textTransform: 'uppercase' }}>Управление заданием на ДО</span>
            {t.can.edit && <Button icon={<EditOutlined />} onClick={() => { setDraft({ vid: t.vid, xyz: t.xyz, eo_id: t.eoId, eo_name: t.eoName, deo: t.deo, location: t.location, brigade: t.brigade,
              template_id: t.templateId, start_date: t.startDate, end_date: t.endDate, is_hs: t.isHs, version: t.version }); setErrors({}); setModal('edit'); }}>Редактировать</Button>}
            {t.can.send && <Button type="primary" icon={<CheckOutlined />} loading={busy} onClick={() => act(() => post(`/tasks/${t.id}/send`, { decision: '', version: t.version }), 'Задание отправлено на согласование')}>Отправить на согласование</Button>}
            {t.can.approve && <Button type="primary" icon={<CheckCircleOutlined />} onClick={() => setModal('approve')}>Внести результат согласования</Button>}
            {t.can.delete && <Button danger icon={<DeleteOutlined />} onClick={() => Modal.confirm({
              title: 'Подтверждение удаления задания на ДО', content: `Задание на ДО № ${t.id} будет удалено. Действие необратимо.`, okText: 'Удалить', okButtonProps: { danger: true }, cancelText: 'Отмена',
              onOk: async () => { try { await del(`/tasks/${t.id}`); message.warning(`Задание на ДО № ${t.id} удалено`); nav('/tasks'); } catch (e) { showError(e); } },
            })}>Удалить</Button>}
            {!t.can.edit && !t.can.send && !t.can.approve && !t.can.delete && <span className="hint">Для вашей роли в статусе «{t.status}» действий нет.</span>}
            <Rule code="R-B301-03" />
          </Space>
          <Space wrap>
            {t.hasResult && <Link to={`/results/${t.id}`}><Button style={{ color: '#1E7B34', borderColor: '#B7E1C0', background: '#E5F4E8' }}>Результат ДО <RightOutlined /></Button></Link>}
            <Button icon={<HistoryOutlined />} onClick={() => setModal('history')}>История</Button>
            <Button icon={<ExportOutlined />} href={app.me!.suiaUrl.replace('{code}', encodeURIComponent(t.xyz))} target="_blank">Перейти к документации объекта в СУИА</Button>
          </Space>
        </div>
        <Block title="Информация о задании на ДО">
          <KV items={[['№', t.id], ['Вид ДО', t.vidDo], ['XYZ', <span className="mono">{t.xyz}</span>], ['Объект ДО', t.eoId ? <Link to={`/eo/${t.eoId}`}>{t.eoName}</Link> : t.eoName],
            ['Эксплуатирующая организация', t.deo], ['Местоположение', t.location], ['Бригада', t.brigade], ['Шаблон', t.template],
            ['Плановое начало ДО', fmtDate(t.startDate)], ['Плановое завершение ДО', fmtDate(t.endDate)], ['Статус', <StatusChip status={t.status} compact />], ['Автор', t.createdBy]]} />
        </Block>
        <Modal open={modal === 'edit'} title="Редактирование задания на ДО" width={720} onCancel={() => setModal('')} okText="Сохранить" cancelText="Отмена" confirmLoading={busy}
          onOk={async () => {
            const e = validateTask(draft!);
            setErrors(e);
            if (Object.keys(e).length) { message.error('Заполните обязательные поля'); return; }
            setBusy(true);
            try { setData(await put(`/tasks/${t.id}`, draft)); setModal(''); message.success('Задание на ДО сохранено'); } catch (err: any) { setErrors(fieldErrors(err)); showError(err); if (err.status === 409) reload(); } finally { setBusy(false); }
          }}>
          {draft && <TaskForm value={draft} onChange={setDraft} errors={errors} />}
        </Modal>
        <DecisionModal open={modal === 'approve'} title="Внесение результата согласования задания на ДО" a="Согласовано" b="Отправить на корректировку" rule="R-B301-04"
          onClose={() => setModal('')}
          onSubmit={async (d, c) => {
            const r = await post(`/tasks/${t.id}/decision`, { decision: d === 'a' ? 'approve' : 'rework', comment: c, version: t.version });
            setData(r);
            message.success(d === 'a' ? 'Задание согласовано. Создан результат ДО в статусе «ПЭ не завершен»' : `Задание № ${t.id} отправлено на корректировку`);
          }} />
        <HistoryModal open={modal === 'history'} onClose={() => setModal('')} rows={t.history} title="История изменения статуса задания на ДО" />
      </div>
    )}</LoadState>
  );
});

export default TaskCard;
