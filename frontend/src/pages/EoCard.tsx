// W-3.3 Карточка единицы оборудования: основное, атрибуты (БДО, только чтение), данные ТС, Δ сравнение замеров, Δ опросный лист, записи о ТС
import { Button, Space, Table, Tabs, Tag } from 'antd';
import { observer } from 'mobx-react-lite';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { get } from '../api';
import LoadState from '../components/LoadState';
import { useLoad } from '../hooks';
import { app } from '../store';
import { BackLink, Block, KV, ScreenTitle, StatusChip, fmtDate, fmtNum } from '../ui';
import { AttrTable, ConfirmSelect } from './TmCard';

const EoCard = observer(() => {
  const { id } = useParams();
  const nav = useNavigate();
  const { data: e, setData, loading, error, reload } = useLoad(() => get(`/eo/${id}`), [id]);
  return (
    <LoadState loading={loading} error={error} reload={reload}>{() => {
      const main = (
        <>
          <Block title="1. Основная информация"><KV items={[['ID записи', <span className="mono">{e.code}</span>], ['Наименование', e.name], ['Объект ремонта', e.repairObject],
            ['Заводской номер', e.factoryNumber || '—'], ['Позиция по схеме', e.position], ['Завод-изготовитель', e.manufacturer], ['Модель', e.model], ['ДЭО', e.deo],
            ['Вышестоящая ЕО', e.parentCode || '—'], ['Техническое место', e.tmId ? <Link className="mono" to={`/tm/${e.tmId}`}>{e.tmCode}</Link> : '—'],
            ['Происхождение', e.origin === 'asupp' ? 'МП-3 «БДО» (АСУ ПП)' : 'Создана в поле (field_created)'], ['Синхронизация с БДО', <StatusChip status={e.sync === 'synced' ? 'Синхронизирована' : e.sync === 'conflict' ? 'Конфликт с БДО' : 'Ожидает добавления в БДО'} compact />]]} /></Block>
          <Block title="2. Атрибуты ЕО (МП-3 «БДО», только чтение — уточнения через опросные листы)"><AttrTable rows={e.attrs} /></Block>
          <Block title="3. Данные тех. состояния">
            <KV items={[['Актуальный статус объекта', e.st || '—'], ['Краткое описание технического состояния объекта', e.desc || '—'],
              ['Статус подтверждения данных о техническом состоянии', <ConfirmSelect value={e.confirm} url={`/eo/${e.id}/confirm`} onDone={(s) => setData({ ...e, confirm: s })} />],
              ['Дата статуса', fmtDate(e.statusDate)], ['Остаточный ресурс, лет', fmtNum(e.life, 1)], ['Дата следующего осмотра / ТО', fmtDate(e.next)],
              ['Метки плана', <>{e.marks.mark3y && <Tag color="blue">3-летний план</Tag>}{e.marks.markNextYear && <Tag color="green">Следующий год</Tag>}{!e.marks.mark3y && !e.marks.markNextYear && '—'}</>]]} />
          </Block>
          {e.children.length > 0 && <Block title={`Входящие ЕО (${e.children.length})`}>
            <Table size="small" rowKey="id" pagination={false} dataSource={e.children} columns={[{ title: 'Код', dataIndex: 'code', render: (v, r: any) => <Link className="mono" to={`/eo/${r.id}`}>{v}</Link> },
              { title: 'Наименование', dataIndex: 'name' }, { title: 'Зав. №', dataIndex: 'factoryNumber' }, { title: 'Тип', dataIndex: 'type' }]} /></Block>}
          <Block title="4. Системные поля"><KV cols={4} items={[['Дата создания записи', fmtDate(e.createdAt)], ['Дата последнего обновления записи', fmtDate(e.updatedAt)], ['Статус записи', e.recordStatus], ['Примечания', e.notes || 'Нет']]} /></Block>
        </>
      );
      const compare = (
        <Block title={<>Динамика толщины стенки по совпадающим точкам контроля (Б318)</>}>
          {e.compare.length ? <div className="grid g3">{e.compare.map((c: any) => (
            <div key={c.point} className="panel" style={{ background: '#F8FAFC', marginBottom: 0 }}>
              <b>{c.point}</b>
              <div className="mono" style={{ fontSize: 12, marginTop: 4 }}>{c.values.map(([y, v]: any) => `${y}: ${fmtNum(v)}`).join(' · ')} мм</div>
              <div className="hint">Скорость изменения {c.rate !== null ? `${fmtNum(c.rate, 3)} мм/год` : '—'}</div>
            </div>))}</div> : <div className="hint">Нет повторных замеров по совпадающим точкам.</div>}
        </Block>
      );
      const records = (
        <Table size="small" rowKey="id" dataSource={e.records} pagination={{ pageSize: 10 }} onRow={(r: any) => ({ onClick: () => nav(`/ts-records/${r.id}`), className: 'clickable-row' })} columns={[
          { title: 'ID записи', dataIndex: 'number', render: (v) => <span className="mono">{v}</span> }, { title: 'Тип записи', dataIndex: 'recordType' }, { title: 'Дата регистрации', dataIndex: 'regDate', render: fmtDate },
          { title: 'Актуальный статус', dataIndex: 'st' }, { title: 'Описание', dataIndex: 'desc', ellipsis: true }, { title: 'Подтверждение', dataIndex: 'confirm', render: (s) => <StatusChip status={s} compact /> }]} />
      );
      return (
        <div>
          <ScreenTitle code="W-3.3" back={<BackLink to="/hierarchy">К иерархии оборудования</BackLink>} title={<Space wrap>Единица оборудования: {e.name}<StatusChip status={e.confirm} /></Space>}
            extra={<>{(app.can('survey') || app.can('plan')) && <Button onClick={() => nav('/surveys')}>Опросный лист</Button>}
              {e.records[0] && <Button type="primary" onClick={() => nav(`/ts-records/${e.records[0].id}`)}>Последняя запись о ТС →</Button>}</>} />
          <div className="panel"><Tabs items={[{ key: 'main', label: 'Основное', children: main }, { key: 'cmp', label: 'Сравнение замеров', children: compare },
            { key: 'rec', label: `Записи о ТС (${e.records.length})`, children: records }]} /></div>
        </div>
      );
    }}</LoadState>
  );
});

export default EoCard;
