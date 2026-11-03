// W-1.4 Карточка шаблона: разделы → подразделы → группы параметров → параметры контроля (табл. 86–89 ТПР)
import { Table } from 'antd';
import { observer } from 'mobx-react-lite';
import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { get } from '../api';
import LoadState from '../components/LoadState';
import { useLoad } from '../hooks';
import { BackLink, Block, KV, ScreenTitle } from '../ui';

const TemplateCard = observer(() => {
  const { id } = useParams();
  const { data: t, loading, error, reload } = useLoad(() => get(`/templates/${id}`), [id]);
  const [code, setCode] = useState('');
  return (
    <LoadState loading={loading} error={error} reload={reload}>{() => {
      const sec = t.sections.find((s: any) => s.code === code) || t.sections[0];
      return (
        <div>
          <ScreenTitle code="W-1.4" back={<BackLink to={`/templates?vid=${t.vid}`}>К списку шаблонов</BackLink>} title={t.name} sub={`${t.vidName} · профиль отчёта ${t.profile}`} />
          <div className="split">
            <div className="panel sec-nav">
              <div className="field-label">Разделы технического отчёта</div>
              {t.sections.map((s: any, i: number) => (
                <button key={s.code} className={`sec-item ${sec.code === s.code ? 'active' : ''}`} onClick={() => setCode(s.code)}>
                  <span>{i + 1}. {s.title}</span><span className="hint">{s.stage === 'ПЭ' ? 'Полевой этап' : 'Камеральный этап'}</span>
                </button>
              ))}
            </div>
            <div>
              <Block title="Раздел"><KV cols={4} items={[['ID записи', sec.id], ['Наименование', sec.title], ['Вид ДО', t.vidName], ['Этап', sec.stage === 'ПЭ' ? 'Полевой этап' : 'Камеральный этап']]} /></Block>
              <Block title="Подраздел"><KV cols={3} items={[['ID записи', sec.subsection.id], ['Наименование', sec.subsection.name], ['Метод контроля (Б315)', sec.subsection.method]]} /></Block>
              <Block title="Группа параметров контроля"><KV cols={3} items={[['ID записи', sec.group.id], ['Наименование', sec.group.name], ['Раздел протокола', sec.group.section]]} /></Block>
              <Block title="Параметры контроля (Б309)">
                <Table size="small" rowKey="id" pagination={false} dataSource={sec.params} scroll={{ x: 900 }} columns={[
                  { title: 'ID записи', dataIndex: 'id', render: (v) => <span className="mono">{v}</span> }, { title: 'Наименование', dataIndex: 'name' },
                  { title: 'Тип данных', dataIndex: 'type' }, { title: 'Мин.', dataIndex: 'min', render: (v) => <span className="mono">{v}</span> },
                  { title: 'Макс.', dataIndex: 'max', render: (v) => <span className="mono">{v}</span> }, { title: 'Ед. изм.', dataIndex: 'unit' },
                  { title: 'Регистрируемая информация', dataIndex: 'reg' }, { title: 'Группа параметров', render: () => 'Стандартная' }]} />
              </Block>
            </div>
          </div>
        </div>
      );
    }}</LoadState>
  );
});

export default TemplateCard;
