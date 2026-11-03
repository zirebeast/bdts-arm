// W-1.1 Список заданий на ДО + модальное окно «Создание задания на ДО»
import { DownloadOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Input, Modal, Segmented, Select, Table, message } from 'antd';
import { observer } from 'mobx-react-lite';
import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { download, get, post } from '../api';
import TaskForm, { TaskFormData, emptyTask, validateTask } from '../components/TaskForm';
import { useLoad } from '../hooks';
import { app } from '../store';
import { ReadOnlyBanner, ScreenTitle, StatusChip, fieldErrors, fmtDate, showError } from '../ui';

const Tasks = observer(() => {
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const vid = sp.get('vid') || 'vessel';
  const mode = sp.get('mode') || 'Активные';
  const [q, setQ] = useState('');
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState<{ sort: string; order: string }>({ sort: 'id', order: 'desc' });
  const { data, loading, reload } = useLoad(() => get('/tasks', { vid, mode, q, page, size: 20, ...sort }), [vid, mode, q, page, sort]);
  const [form, setForm] = useState<TaskFormData | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (sp.get('create') && app.can('task.create')) {
      setForm({ ...emptyTask(sp.get('vid') || 'tpa'), xyz: sp.get('xyz') || '', eo_name: sp.get('eo') || '', location: sp.get('loc') || '', deo: sp.get('deo') || app.me?.deo || '', is_hs: sp.get('hs') === '1', brigade: sp.get('hs') === '1' ? 'Бригада ДЭО (хозспособ)' : '' });
      sp.delete('create');
      setSp(sp, { replace: true });
    }
  }, []);

  const create = async () => {
    const e = validateTask(form!);
    setErrors(e);
    if (Object.keys(e).length) { message.error('Заполните обязательные поля'); return; }
    setBusy(true);
    try {
      const t = await post('/tasks', form);
      message.success(`Задание на ДО № ${t.id} создано в статусе «Черновик»`);
      setForm(null);
      nav(`/tasks/${t.id}`);
    } catch (err) { setErrors(fieldErrors(err)); showError(err); } finally { setBusy(false); }
  };

  const cols: any[] = [
    { title: '№', dataIndex: 'id', key: 'id', sorter: true, width: 70, render: (v: number) => <b className="mono" style={{ color: '#1F5FAD' }}>{v}</b> },
    { title: 'XYZ', dataIndex: 'xyz', key: 'xyz', sorter: true, render: (v: string) => <span className="mono">{v}</span> },
    { title: 'Объект ДО', dataIndex: 'eoName', key: 'eoName', sorter: true },
    { title: 'Эксплуатирующая организация', dataIndex: 'deo', key: 'deo', sorter: true },
    { title: 'Местоположение', dataIndex: 'location', ellipsis: true },
    { title: 'Бригада', dataIndex: 'brigade' },
    { title: 'Шаблон', dataIndex: 'template', ellipsis: true },
    { title: 'Плановое начало ДО', dataIndex: 'startDate', key: 'startDate', sorter: true, render: fmtDate },
    { title: 'Плановое завершение ДО', dataIndex: 'endDate', key: 'endDate', sorter: true, render: fmtDate },
    { title: 'Статус', dataIndex: 'status', key: 'status', sorter: true, render: (s: string) => <StatusChip status={s} compact /> },
  ];
  return (
    <div>
      <ScreenTitle code="W-1.1" title="Задания на ДО" extra={<>
        <Button icon={<DownloadOutlined />} onClick={() => download('/tasks/export.xlsx', { vid, mode, q })}>Сохранить в Excel</Button>
        <Button icon={<ReloadOutlined />} onClick={reload} />
        {app.can('task.create') && <Button type="primary" icon={<PlusOutlined />} onClick={() => { setErrors({}); setForm(emptyTask(vid)); }}>Создать задание на ДО</Button>}
      </>} />
      <ReadOnlyBanner screen="W-1.1" />
      <div className="toolbar">
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          <span className="field-label" style={{ margin: 0 }}>Вид ДО</span>
          <Select style={{ width: 420, maxWidth: '100%' }} value={vid} options={app.refs!.vids.map((v) => ({ value: v.key, label: v.name }))}
            onChange={(v) => { sp.set('vid', v); setSp(sp); setPage(1); }} />
          <Segmented value={mode} options={['Активные', 'Выполненные']} onChange={(v) => { sp.set('mode', v as string); setSp(sp); setPage(1); }} />
        </div>
        <Input.Search allowClear placeholder="Поиск: XYZ, объект, местоположение" style={{ width: 320 }} onSearch={(v) => { setQ(v); setPage(1); }} />
      </div>
      <Table size="small" rowKey="id" loading={loading} columns={cols} dataSource={data?.items || []} scroll={{ x: 1300 }}
        locale={{ emptyText: 'Заданий на ДО выбранного вида нет' }}
        pagination={{ current: page, pageSize: 20, total: data?.total || 0, onChange: setPage, showTotal: (t) => `Всего: ${t}` }}
        onChange={(_, __, s: any) => setSort(s.order ? { sort: s.columnKey, order: s.order === 'ascend' ? 'asc' : 'desc' } : { sort: 'id', order: 'desc' })}
        onRow={(r) => ({ onClick: () => nav(`/tasks/${r.id}`), className: 'clickable-row', tabIndex: 0, onKeyDown: (e) => { if (e.key === 'Enter') nav(`/tasks/${r.id}`); } })} />
      <Modal open={!!form} title={form?.is_hs ? "Создание задания на ДО хозяйственным способом" : "Создание задания на ДО"} width={720} onCancel={() => setForm(null)} onOk={create} okText="Создать" cancelText="Отмена" confirmLoading={busy} destroyOnClose>
        {form && <TaskForm value={form} onChange={setForm} errors={errors} />}
      </Modal>
    </div>
  );
});

export default Tasks;
