// W-7.1 Настройки модуля: маршрут согласования (версии), схема оповещений, права доступа, отчётный период, планирование, интеграции
import { ArrowDownOutlined, ArrowUpOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, DatePicker, Input, InputNumber, Select, Space, Switch, Table, Tabs, Tag, message } from 'antd';
import dayjs from 'dayjs';
import { observer } from 'mobx-react-lite';
import { useEffect, useState } from 'react';
import { get, post, put } from '../api';
import LoadState from '../components/LoadState';
import { useLoad } from '../hooks';
import { ScreenTitle, StatusChip, fmtDateTime, showError } from '../ui';

const Settings = observer(() => {
  const { data, loading, error, reload } = useLoad(() => get('/settings'), []);
  const integ = useLoad(() => get('/integrations'), []);
  const [s, setS] = useState<any>(null);
  const [entity, setEntity] = useState('Результат ДО');
  useEffect(() => { if (data) setS(JSON.parse(JSON.stringify(data))); }, [data]);
  const save = async (key: string, value: any, ok = 'Настройки сохранены') => {
    try { await put(`/settings/${key}`, value); message.success(ok); reload(); } catch (e) { showError(e); }
  };
  return (
    <LoadState loading={loading || !s} error={error} reload={reload}>{() => {
      const locked = !s.canEdit;
      const steps = s.routes.steps || [];
      const mine = steps.filter((x: any) => x.entity === entity);
      const move = (st: any, dir: number) => {
        const i = steps.indexOf(st); const j = steps.indexOf(mine[mine.indexOf(st) + dir]);
        const n = [...steps]; [n[i], n[j]] = [n[j], n[i]];
        setS({ ...s, routes: { ...s.routes, steps: n } });
      };
      const setStep = (st: any, p: any) => setS({ ...s, routes: { ...s.routes, steps: steps.map((x: any) => (x.id === st.id ? { ...x, ...p } : x)) } });
      return (
        <div>
          <ScreenTitle code="W-7.1" title="Настройка модуля (интерфейс администратора)" sub={locked ? 'Доступно для изменения роли «Администратор модуля». Для вашей роли — только просмотр.' : 'Изменения применяются к новым документам.'} />
          <div className="panel"><Tabs items={[
            { key: 'route', label: 'Маршрут согласования', children: <>
              <Space wrap style={{ marginBottom: 10 }}>
                <div><div className="field-label">Сущность</div><Select style={{ width: 200 }} value={entity} onChange={setEntity} options={['Задание на ДО', 'Результат ДО'].map((x) => ({ value: x, label: x }))} /></div>
                <div><div className="field-label">Версия маршрута</div><Tag className="mono">{s.routes.version}</Tag> <span className="hint">действует с {s.routes.since || '—'}; начатые документы завершают маршрут по своей версии</span></div>
              </Space>
              <Table size="small" rowKey="id" pagination={false} dataSource={mine} columns={[
                { title: 'Этап', dataIndex: 'stage' }, { title: 'Шаг', dataIndex: 'step' }, { title: 'Ответственная роль', dataIndex: 'role' },
                { title: 'Порядок', render: (_: any, st: any) => <Select disabled={locked} style={{ width: 210 }} value={st.mode} onChange={(v) => setStep(st, { mode: v })} options={['Последовательно', 'Параллельно с предыдущим'].map((x) => ({ value: x, label: x }))} /> },
                { title: 'Срок на шаге', render: (_: any, st: any) => <Input disabled={locked} style={{ width: 120 }} value={st.sla} onChange={(e) => setStep(st, { sla: e.target.value })} /> },
                { title: 'Условие', dataIndex: 'cond' },
                ...(!locked ? [{ title: '', render: (_: any, st: any) => <Space><Button size="small" icon={<ArrowUpOutlined />} disabled={mine.indexOf(st) === 0} onClick={() => move(st, -1)} /><Button size="small" icon={<ArrowDownOutlined />} disabled={mine.indexOf(st) === mine.length - 1} onClick={() => move(st, 1)} /></Space> }] : [])]} />
              {!locked && <Space style={{ marginTop: 10 }}><Button onClick={() => save('routes', s.routes)}>Сохранить</Button><Button type="primary" onClick={() => save('routes', { ...s.routes, newVersion: true, since: dayjs().format('YYYY-MM-DD') }, 'Сохранено как новая версия маршрута')}>Сохранить как новую версию</Button>
                <Button onClick={() => { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([JSON.stringify(s.routes, null, 2)], { type: 'application/json' })); a.download = 'routes.json'; a.click(); }}>Экспорт настроек</Button></Space>}
            </> },
            { key: 'notify', label: 'Схема оповещения', children: <>
              <Table size="small" rowKey="id" pagination={false} dataSource={s.notify_rules.items} scroll={{ x: 1300 }} columns={[
                { title: 'Наименование правила', dataIndex: 'name' }, { title: 'Сущность', dataIndex: 'entity' }, { title: 'Атрибут', dataIndex: 'attr' }, { title: 'Условие срабатывания', dataIndex: 'cond' },
                { title: 'Роли для оповещения', dataIndex: 'role' }, { title: 'Способ', dataIndex: 'channel' }, { title: 'Шаблон уведомления', dataIndex: 'tpl', render: (v) => <span className="hint">{v}</span> },
                { title: 'Вкл.', render: (_: any, r: any) => <Switch size="small" disabled={locked} checked={r.on} onChange={(v) => setS({ ...s, notify_rules: { items: s.notify_rules.items.map((x: any) => (x.id === r.id ? { ...x, on: v } : x)) } })} /> }]} />
              {!locked && <Button style={{ marginTop: 10 }} type="primary" onClick={() => save('notify_rules', s.notify_rules)}>Сохранить</Button>}
            </> },
            { key: 'access', label: 'Права доступа', children: <>
              <p className="hint">Роли назначаются группами каталога пользователей (Keycloak / LDAP): группа → бизнес-роль МП-3.5. Ниже — текущие назначения демо-пользователей.</p>
              <Table size="small" rowKey="code" pagination={false} dataSource={s.roles} columns={[{ title: 'Бизнес-роль', dataIndex: 'label' }, { title: 'Техническое имя', dataIndex: 'code', render: (v) => <span className="mono">{v}</span> },
                { title: 'Назначены пользователи', dataIndex: 'users', render: (u: string[]) => u.join(', ') || '—' }]} />
            </> },
            { key: 'period', label: 'Отчётный период', children: <Space wrap align="end">
              <div><div className="field-label">Дата закрытия отчётного периода</div><DatePicker disabled={locked} format="DD.MM.YYYY" value={s.report_period.closed_to ? dayjs(s.report_period.closed_to) : null}
                onChange={(d) => setS({ ...s, report_period: { closed_to: d ? d.format('YYYY-MM-DD') : '' } })} /></div>
              <span className="hint" style={{ maxWidth: 420 }}>Записи о ТС с датой регистрации до этой даты доступны только для чтения.</span>
              {!locked && <Button type="primary" onClick={() => save('report_period', s.report_period, 'Отчётный период сохранён')}>Сохранить</Button>}
            </Space> },
            { key: 'plan', label: 'Планирование', children: <Space wrap align="end">
              <div><div className="field-label">Мощность бригад, ЕО в месяц (дашборд D1)</div><InputNumber disabled={locked} min={1} value={s.planning.brigade_capacity} onChange={(v) => setS({ ...s, planning: { ...s.planning, brigade_capacity: v } })} /></div>
              {!locked && <Button type="primary" onClick={() => save('planning', s.planning)}>Сохранить</Button>}
            </Space> },
            { key: 'integrations', label: 'Интеграции', children: <LoadState loading={integ.loading} error={integ.error} reload={integ.reload}>{() => <>
              <Table size="small" rowKey="flow" pagination={false} title={() => <b>Порты интеграций и активные адаптеры</b>} dataSource={integ.data.adapters} columns={[
                { title: 'Поток', dataIndex: 'flow' }, { title: 'Направление', dataIndex: 'direction', render: (d) => (d === 'in' ? 'Входящий' : 'Исходящий') }, { title: 'Система / адаптер', dataIndex: 'system' },
                { title: 'Режим', dataIndex: 'mode', render: (m) => <Tag color={m === 'mock' || m === 'dev' ? 'orange' : 'green'} className="mono">{m}</Tag> }]} />
              <Space style={{ margin: '12px 0' }}>Очередь outbox: {Object.entries(integ.data.outbox).map(([k, v]: any) => <Tag key={k}>{k}: {v}</Tag>)}
                {!locked && <Button size="small" icon={<ReloadOutlined />} onClick={async () => { const r = await post('/integrations/outbox/retry'); message.info(`Доставлено событий: ${r.sent}`); integ.reload(); }}>Доставить повторно</Button>}</Space>
              <Table size="small" rowKey="id" pagination={{ pageSize: 15 }} dataSource={integ.data.log} title={() => <b>Журнал обменов</b>} columns={[
                { title: 'Дата', dataIndex: 'date', render: fmtDateTime }, { title: 'Напр.', dataIndex: 'direction', render: (d) => (d === 'in' ? '⇣ вход' : '⇡ выход') }, { title: 'Поток', dataIndex: 'flow' },
                { title: 'Система', dataIndex: 'system' }, { title: 'Записей', dataIndex: 'count' }, { title: 'Результат', dataIndex: 'status', render: (x) => <StatusChip status={x} compact /> }, { title: 'Инициатор', dataIndex: 'user' }]} />
            </>}</LoadState> },
          ]} /></div>
        </div>
      );
    }}</LoadState>
  );
});

export default Settings;
