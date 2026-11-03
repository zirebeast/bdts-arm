// W-3.1 Иерархия оборудования: ТМ → ЕО → записи о ТС (ленивая подгрузка узлов), группировки (Δ), агрегат ТС по R-B316-03
import { DatabaseOutlined, EnvironmentOutlined, FileTextOutlined, FolderOutlined } from '@ant-design/icons';
import { Select, Space, Table } from 'antd';
import { observer } from 'mobx-react-lite';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { get } from '../api';
import { app } from '../store';
import { Rule, ScreenTitle, StatusChip, fmtDate, fmtNum } from '../ui';

const ICON: Record<string, any> = { 'ТМ': <EnvironmentOutlined style={{ color: '#1F5FAD' }} />, 'ЕО': <DatabaseOutlined style={{ color: '#1E7B34' }} />, 'ТС': <FileTextOutlined style={{ color: '#5A6472' }} />, GROUP: <FolderOutlined /> };
const prep = (rows: any[]) => rows.map((r) => ({ ...r, children: r.hasChildren ? [] : undefined }));

const Hierarchy = observer(() => {
  const nav = useNavigate();
  const [group, setGroup] = useState('tm');
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<string[]>([]);
  useEffect(() => {
    setLoading(true);
    setLoaded(new Set());
    setExpanded([]);
    get('/hierarchy', { group }).then((r) => setRows(prep(r))).finally(() => setLoading(false));
  }, [group]);
  const insert = (list: any[], key: string, kids: any[]): any[] => list.map((r) => (r.key === key ? { ...r, children: kids.length ? prep(kids) : undefined } : r.children ? { ...r, children: insert(r.children, key, kids) } : r));
  const onExpand = async (exp: boolean, rec: any) => {
    setExpanded((e) => (exp ? [...e, rec.key] : e.filter((k) => k !== rec.key)));
    if (exp && !loaded.has(rec.key)) {
      const kids = await get('/hierarchy', { node: rec.key, group });
      setRows((r) => insert(r, rec.key, kids));
      setLoaded((s) => new Set(s).add(rec.key));
    }
  };
  const open = (r: any) => (r.type === 'ТМ' ? nav(`/tm/${r.id}`) : r.type === 'ЕО' ? nav(`/eo/${r.id}`) : r.type === 'ТС' ? nav(`/ts-records/${r.id}`) : null);
  const cols: any[] = [
    { title: '1. Ключевые идентификаторы оборудования', children: [
      { title: 'ID записи', key: 'id', width: 300, fixed: 'left', render: (_: any, r: any) => <Space size={6}>{ICON[r.type]}{r.type === 'GROUP' ? <b>{r.name}</b> : <a className="mono" onClick={(e) => { e.stopPropagation(); open(r); }}>{r.type === 'ТС' ? r.number : r.code}</a>}</Space> },
      { title: 'Тип строки', dataIndex: 'type', width: 80, render: (t: string) => (t === 'GROUP' ? '' : t) },
      { title: 'Код технического места', width: 230, render: (_: any, r: any) => <span className="mono">{r.type === 'ТМ' ? r.code : r.tmCode}</span> },
      { title: 'Наименование технического места', width: 200, render: (_: any, r: any) => (r.type === 'ТМ' ? r.name : r.tmName) },
      { title: 'Название единицы оборудования', width: 230, render: (_: any, r: any) => (r.type === 'ЕО' ? r.name : r.type === 'ТС' ? r.eoName : '—') },
      { title: 'Организация', dataIndex: 'deo', width: 90 },
      { title: 'Инвентарный номер', dataIndex: 'inventory', width: 120, render: (v: string) => <span className="mono">{v || '—'}</span> },
    ] },
    { title: '2. Данные тех. состояния', children: [
      { title: 'Дата фиксации', width: 110, render: (_: any, r: any) => fmtDate(r.fix || r.regDate) },
      { title: 'Дата следующего осмотра/ ТО', dataIndex: 'next', width: 120, render: fmtDate },
      { title: 'Актуальный статус объекта', dataIndex: 'st', width: 170, render: (v: string) => v || '—' },
      { title: 'Оценка износа, %', dataIndex: 'wear', width: 90, render: (v: any) => <span className="mono">{fmtNum(v)}</span> },
      { title: 'Краткое описание ТС', dataIndex: 'desc', width: 240, ellipsis: true },
      { title: 'Статус подтверждения', dataIndex: 'confirm', width: 235, render: (s: string, r: any) => (r.type === 'GROUP' ? '' : <StatusChip status={s} compact />) },
      { title: 'Дата статуса', dataIndex: 'statusDate', width: 110, render: fmtDate },
    ] },
    { title: '3. Системные поля', children: [
      { title: 'Дата создания записи', dataIndex: 'createdAt', width: 110, render: fmtDate },
      { title: 'Дата последнего обновления', dataIndex: 'updatedAt', width: 120, render: fmtDate },
      { title: 'Статус записи', dataIndex: 'recordStatus', width: 110 },
    ] },
  ];
  return (
    <div>
      <ScreenTitle code="W-3.1" title="Иерархия оборудования: ТМ → ЕО → записи о техническом состоянии" extra={<Space>
        <span className="hint">Группировка</span>
        <Select style={{ width: 220 }} value={group} onChange={setGroup} options={[{ value: 'tm', label: 'По иерархии ТМ' }, { value: 'deo', label: 'От ДО (ДЭО)' }, { value: 'class', label: 'По классу оборудования' }, { value: 'model', label: 'По модели' }]} />
      </Space>} />
      <Table size="small" rowKey="key" bordered loading={loading} columns={cols} dataSource={rows} pagination={false} scroll={{ x: 2400, y: 'calc(100vh - 330px)' }}
        expandable={{ expandedRowKeys: expanded, onExpand }} onRow={(r) => ({ onDoubleClick: () => open(r) })} />
      <p className="hint" style={{ marginTop: 8 }}>Данные тех. состояния ТМ и ЕО собираются по каждому атрибуту из самой поздней записи о ТС, где атрибут заполнен<Rule code="R-B316-03" />. Нажмите на ID, чтобы открыть карточку ТМ, ЕО или записи о ТС; ▸ — раскрыть узел. Атрибуты из БДО доступны только для чтения<Rule code="D-HS-01" />.</p>
    </div>
  );
});

export default Hierarchy;
