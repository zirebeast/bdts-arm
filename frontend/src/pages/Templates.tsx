// W-1.3 Шаблоны заданий на ДО (R-B302-01: настраиваются разработчиками, пользователем не изменяются)
import { Select, Table } from 'antd';
import { observer } from 'mobx-react-lite';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { get } from '../api';
import { useLoad } from '../hooks';
import { app } from '../store';
import { ScreenTitle } from '../ui';

const Templates = observer(() => {
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const vid = sp.get('vid') || 'vessel';
  const { data, loading } = useLoad(() => get('/templates', { vid }), [vid]);
  return (
    <div>
      <ScreenTitle code="W-1.3" title="Шаблоны заданий на ДО" sub="Шаблоны настраиваются разработчиками при внедрении и пользователями не изменяются." />
      <div className="toolbar">
        <span className="field-label" style={{ margin: 0 }}>Вид ДО</span>
        <Select style={{ width: 460, maxWidth: '100%' }} value={vid} options={app.refs!.vids.map((v) => ({ value: v.key, label: v.name }))} onChange={(v) => { sp.set('vid', v); setSp(sp); }} />
      </div>
      <Table size="small" rowKey="id" loading={loading} dataSource={data || []} pagination={false}
        locale={{ emptyText: 'Для ВТД шаблоны не предусмотрены: технический отчёт загружается в результат ДО файлом.' }}
        columns={[{ title: '№', dataIndex: 'no', width: 80, render: (v) => <b className="mono" style={{ color: '#1F5FAD' }}>{v}</b> }, { title: 'Название шаблона', dataIndex: 'name' }]}
        onRow={(r: any) => ({ onClick: () => nav(`/templates/${r.id}`), className: 'clickable-row' })} />
    </div>
  );
});

export default Templates;
