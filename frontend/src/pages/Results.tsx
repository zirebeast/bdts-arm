// W-2.1 Список результатов ДО; W-2.5 (Δ) — результаты ДО хозяйственным способом (та же карточка W-2.2, признак «Хозспособ»)
import { PlusOutlined } from '@ant-design/icons';
import { Button, Input, Segmented, Select, Table } from 'antd';
import { observer } from 'mobx-react-lite';
import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { get } from '../api';
import { useLoad } from '../hooks';
import { app } from '../store';
import { ScreenTitle, StatusChip, fmtDate } from '../ui';

const Results = observer(({ hs }: { hs?: boolean }) => {
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const vid = sp.get('vid') || (hs ? '' : 'vessel');
  const mode = sp.get('mode') || 'В процессе';
  const [q, setQ] = useState('');
  const [page, setPage] = useState(1);
  const { data, loading } = useLoad(() => get('/results', { vid, mode, q, page, size: 20, ...(hs ? { hs: true } : {}) }), [vid, mode, q, page, hs]);
  const cols: any[] = [
    { title: '№', dataIndex: 'id', width: 70, render: (v: number) => <b className="mono" style={{ color: '#1F5FAD' }}>{v}</b> },
    { title: 'XYZ', dataIndex: 'xyz', render: (v: string) => <span className="mono">{v}</span> },
    { title: 'Объект ДО', dataIndex: 'eoName' }, { title: 'Эксплуатирующая организация', dataIndex: 'deo' },
    { title: 'Местоположение', dataIndex: 'location', ellipsis: true }, { title: 'Бригада', dataIndex: 'brigade' }, { title: 'Шаблон', dataIndex: 'template', ellipsis: true },
    { title: 'Плановое начало ДО', dataIndex: 'startDate', render: fmtDate }, { title: 'Плановое завершение ДО', dataIndex: 'endDate', render: fmtDate },
    { title: 'Статус', dataIndex: 'resultStatus', render: (s: string) => <StatusChip status={s} compact /> },
  ];
  return (
    <div>
      <ScreenTitle code={hs ? 'W-2.5' : 'W-2.1'} title={hs ? <>Результаты ДО хозяйственным способом</> : 'Результаты ДО'}
        sub={hs ? 'ДО силами ДЭО ведётся в той же карточке результата ДО: разделы по шаблону, ПЭ, КП, формирование ТО и согласование. Отличие — исполнитель (бригада ДЭО) и признак «Хозспособ».' : undefined}
        extra={hs && app.can('task.create') ? <Button type="primary" icon={<PlusOutlined />} onClick={() => nav('/tasks?create=1&vid=vessel&hs=1')}>Задание хозспособом</Button> : undefined} />
      <div className="toolbar">
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          <span className="field-label" style={{ margin: 0 }}>Вид ДО</span>
          <Select style={{ width: 420, maxWidth: '100%' }} value={vid} allowClear={hs} placeholder="Все виды ДО"
            options={app.refs!.vids.map((v) => ({ value: v.key, label: v.name }))} onChange={(v) => { if (v) sp.set('vid', v); else sp.delete('vid'); setSp(sp); setPage(1); }} />
          <Segmented value={mode} options={['В процессе', 'Получены']} onChange={(v) => { sp.set('mode', v as string); setSp(sp); setPage(1); }} />
        </div>
        <Input.Search allowClear placeholder="Поиск: XYZ, объект" style={{ width: 280 }} onSearch={(v) => { setQ(v); setPage(1); }} />
      </div>
      <Table size="small" rowKey="id" loading={loading} columns={cols} dataSource={data?.items || []} scroll={{ x: 1300 }}
        locale={{ emptyText: 'Результатов ДО выбранного вида нет' }}
        pagination={{ current: page, pageSize: 20, total: data?.total || 0, onChange: setPage, showTotal: (t) => `Всего: ${t}` }}
        onRow={(r) => ({ onClick: () => nav(`/results/${r.id}`), className: 'clickable-row' })} />
    </div>
  );
});

export default Results;
