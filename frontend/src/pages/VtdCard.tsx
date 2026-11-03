// W-6.2 (Δ) Карточка участка ВТД: камеры СОД, отчёты ВТД (файлы, OQ-13), история участка
import { DownloadOutlined } from '@ant-design/icons';
import { Table, Tabs, Tag } from 'antd';
import { observer } from 'mobx-react-lite';
import { Link, useParams } from 'react-router-dom';
import { download, get } from '../api';
import LoadState from '../components/LoadState';
import { useLoad } from '../hooks';
import { BackLink, Block, KV, ScreenTitle, StatusChip } from '../ui';
import { LinearScheme } from './Vtd';

const VtdCard = observer(() => {
  const { id } = useParams();
  const { data: s, loading, error, reload } = useLoad(() => get(`/vtd/${id}`), [id]);
  const all = useLoad(() => get('/vtd'), []);
  return (
    <LoadState loading={loading} error={error} reload={reload}>{() => (
      <div>
        <ScreenTitle code="W-6.2" back={<BackLink to="/vtd">К реестру участков</BackLink>} title={<>Участок ВТД <span className="mono">{s.code}</span> · {s.kmFrom}–{s.kmTo} км</>} extra={<StatusChip status={s.status} />} />
        {s.overlaps.length > 0 && <div className="banner-warn">Пересечение границ (D-VTD-01): {s.overlaps.join('; ')}</div>}
        {all.data && <div className="panel"><LinearScheme items={all.data.items.filter((x: any) => x.pipeline === s.pipeline)} active={s.id} /></div>}
        <Block title="Атрибуты участка"><KV cols={3} items={[['Магистральный газопровод', s.pipeline], ['Тип участка', s.type], ['ДЭО', s.deo], ['Техническое место', <span className="mono">{s.tm}</span>], ['Смежный участок', s.adjacent || '—'], ['Примечания', s.notes || '—']]} /></Block>
        <div className="panel"><Tabs items={[
          { key: 'ch', label: 'Камеры СОД', children: <Table size="small" rowKey="id" pagination={false} dataSource={s.chambers} columns={[
            { title: 'Код', dataIndex: 'code', render: (v) => <span className="mono">{v}</span> }, { title: 'Тип', dataIndex: 'kind', render: (k) => (k === 'launch' ? 'Камера запуска' : 'Камера приёма') },
            { title: 'Км', dataIndex: 'km' }, { title: 'Постоянная', dataIndex: 'permanent', render: (v) => (v ? 'Да' : 'Временная') }, { title: 'Состояние', dataIndex: 'active', render: (v) => (v ? <Tag color="green">Активна</Tag> : <Tag>Неактивна (снята)</Tag>) }]} /> },
          { key: 'files', label: 'Отчёты ВТД/ПВО (файлы)', children: <Table size="small" rowKey="id" pagination={false} dataSource={s.files} locale={{ emptyText: 'Отчёты ВТД загружаются в результат ДО вида «ВТД» файлом (OQ-13)' }} columns={[
            { title: 'Файл', dataIndex: 'name', render: (v, f: any) => <a onClick={() => download(`/files/${f.id}`)}><DownloadOutlined /> {v}</a> }, { title: 'Результат ДО', dataIndex: 'task', render: (t) => <Link to={`/results/${t}`}>по заданию № {t}</Link> },
            { title: 'Статус', dataIndex: 'status', render: (x) => <StatusChip status={x} compact /> }]} /> },
          { key: 'hist', label: 'История участка', children: <Table size="small" rowKey={(_, i) => String(i)} pagination={false} dataSource={s.history} columns={[{ title: 'Дата', dataIndex: 'date' }, { title: 'Пользователь', dataIndex: 'user' }, { title: 'Событие', dataIndex: 'text' }]} /> },
        ]} /></div>
      </div>
    )}</LoadState>
  );
});

export default VtdCard;
