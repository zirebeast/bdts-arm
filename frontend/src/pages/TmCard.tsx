// W-3.2 Карточка технического места: основная информация, атрибуты, данные ТС (подтверждение — только Б316-14, R-B316-01), системные поля
import { Select, Table, message } from 'antd';
import { observer } from 'mobx-react-lite';
import { Link, useParams } from 'react-router-dom';
import { get, post } from '../api';
import LoadState from '../components/LoadState';
import { useLoad } from '../hooks';
import { app } from '../store';
import { BackLink, Block, KV, Rule, ScreenTitle, StatusChip, fmtDate, showError } from '../ui';

export function ConfirmSelect({ value, url, onDone }: { value: string; url: string; onDone: (s: string) => void }) {
  return (
    <span>
      <Select style={{ width: 220 }} value={value} disabled={!app.can('ts.confirm')} options={['Подтверждено', 'Требует подтверждения'].map((v) => ({ value: v, label: v }))}
        onChange={async (v) => { try { await post(url, { status: v }); onDone(v); message.success('Статус подтверждения сохранён'); } catch (e) { showError(e); } }} />
      <Rule code="R-B316-01" />
    </span>
  );
}

export const AttrTable = ({ rows }: { rows: any[] }) => (
  <Table size="small" pagination={false} rowKey={(r: any) => r[0]} dataSource={rows} columns={[
    { title: 'Код', dataIndex: 0, render: (v) => <span className="mono">{v}</span> }, { title: 'Наименование', dataIndex: 1 }, { title: 'Значение', dataIndex: 2, render: (v) => v || '—' }, { title: 'Единица измерения', dataIndex: 3 }]} />
);

const TmCard = observer(() => {
  const { id } = useParams();
  const { data: t, setData, loading, error, reload } = useLoad(() => get(`/tm/${id}`), [id]);
  return (
    <LoadState loading={loading} error={error} reload={reload}>{() => (
      <div>
        <ScreenTitle code="W-3.2" back={<BackLink to="/hierarchy">К иерархии оборудования</BackLink>} title={<>Техническое место: <span className="mono">{t.code}</span> «{t.name}»</>} extra={<StatusChip status={t.confirm} />} />
        <Block title="1. Основная информация"><KV items={[['ID записи', t.id], ['Код позиции в semantic', <span className="mono">{t.semanticCode}</span>], ['Наименование', t.name],
          ['Код технического места', <span className="mono">{t.code}</span>], ['ДЭО', t.deo], ['Вышестоящее ТМ', t.parentCode || '—'], ['Наименование объекта (согласно СОР)', t.sorName]]} /></Block>
        <Block title="2. Атрибуты ТМ (МП-3 «БДО», только чтение)"><AttrTable rows={t.attrs} /></Block>
        <Block title="3. Данные тех. состояния">
          <KV items={[['Актуальный статус объекта', t.st || '—'], ['Краткое описание технического состояния объекта', t.desc || '—'],
            ['Статус подтверждения данных о техническом состоянии', <ConfirmSelect value={t.confirm} url={`/tm/${t.id}/confirm`} onDone={(s) => setData({ ...t, confirm: s })} />],
            ['Дата статуса', fmtDate(t.statusDate)], ['Дата фиксации', fmtDate(t.fix)], ['Дата следующего осмотра / ТО', fmtDate(t.next)]]} />
        </Block>
        <Block title={`Единицы оборудования ТМ (${t.eoCount})`}>
          <Table size="small" rowKey="id" pagination={false} dataSource={t.eos} columns={[
            { title: 'Код', dataIndex: 'code', render: (v, r: any) => <Link className="mono" to={`/eo/${r.id}`}>{v}</Link> }, { title: 'Наименование', dataIndex: 'name' }, { title: 'Класс', dataIndex: 'class' },
            { title: 'Актуальный статус', dataIndex: 'st' }, { title: 'След. ТД', dataIndex: 'next', render: fmtDate }, { title: 'Подтверждение', dataIndex: 'confirm', render: (s) => <StatusChip status={s} compact /> }]} />
        </Block>
        <Block title="4. Системные поля"><KV cols={4} items={[['Дата создания записи', fmtDate(t.createdAt)], ['Дата последнего обновления записи', fmtDate(t.updatedAt)], ['Статус записи', t.recordStatus], ['Примечания', t.notes || 'Нет']]} /></Block>
        <div style={{ textAlign: 'right' }}><Link to="/ts-records">Реестр записей о техническом состоянии →</Link></div>
      </div>
    )}</LoadState>
  );
});

export default TmCard;
