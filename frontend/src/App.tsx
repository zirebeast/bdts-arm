// W-0.1 Оболочка модуля: ролевое меню (240/80 px) с нижней зоной профиля и уведомлений, crumbs по истории посещений, маршруты экранов
import {
  AppstoreOutlined, AuditOutlined, BarChartOutlined, BookOutlined, ClusterOutlined, CloudDownloadOutlined, DatabaseOutlined,
  EditOutlined, EnvironmentOutlined, FileDoneOutlined, FileTextOutlined, FormOutlined, HistoryOutlined, HomeOutlined, LogoutOutlined,
  MenuFoldOutlined, MenuUnfoldOutlined, MessageOutlined, NodeIndexOutlined, ProfileOutlined, SearchOutlined, SettingOutlined, SlidersOutlined, SnippetsOutlined, StarFilled,
  UnorderedListOutlined, UserOutlined,
} from '@ant-design/icons';
import { Badge, Button, Dropdown, Empty, Menu, Popover, Result, Segmented, Space, Spin, Switch, Tag, Tooltip } from 'antd';
import { observer } from 'mobx-react-lite';
import React, { Suspense, lazy, useEffect, useState } from 'react';
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { logout, relogin } from './auth';
import { app } from './store';
import { fmtDateTime } from './ui';

const P = (f: () => Promise<any>) => lazy(f);
const pages = {
  Cabinet: P(() => import('./pages/Cabinet')), Profile: P(() => import('./pages/Profile')), Search: P(() => import('./pages/Search')),
  Tasks: P(() => import('./pages/Tasks')), TaskCard: P(() => import('./pages/TaskCard')), Templates: P(() => import('./pages/Templates')),
  TemplateCard: P(() => import('./pages/TemplateCard')), Results: P(() => import('./pages/Results')), ResultCard: P(() => import('./pages/ResultCard')),
  Reports: P(() => import('./pages/Reports')), ReportCard: P(() => import('./pages/ReportCard')), Hierarchy: P(() => import('./pages/Hierarchy')),
  TmCard: P(() => import('./pages/TmCard')), EoCard: P(() => import('./pages/EoCard')), TsRecords: P(() => import('./pages/TsRecords')),
  TsRecordCard: P(() => import('./pages/TsRecordCard')), Logs: P(() => import('./pages/Logs')), Planning: P(() => import('./pages/Planning')),
  Surveys: P(() => import('./pages/Surveys')), Analytics: P(() => import('./pages/Analytics')), Dashboards: P(() => import('./pages/Dashboards')),
  Nsi: P(() => import('./pages/Nsi')), Dict38: P(() => import('./pages/Dict38')), Vtd: P(() => import('./pages/Vtd')), VtdCard: P(() => import('./pages/VtdCard')),
  Settings: P(() => import('./pages/Settings')), PlanLoad: P(() => import('./pages/PlanLoad')), Objects: P(() => import('./pages/Objects')),
  ObjectCard: P(() => import('./pages/ObjectCard')),
};

type Item = { key: string; code: string; label: string; icon: React.ReactNode; show?: () => boolean };
const NAV: { group: string; items: Item[] }[] = [
  { group: 'Обзор и поиск', items: [
    { key: '/cabinet', code: 'W-0.4', label: 'Личный кабинет', icon: <HomeOutlined /> },
    { key: '/search', code: 'W-0.2', label: 'Поиск объектов', icon: <SearchOutlined /> },
  ] },
  { group: 'Процесс ДО', items: [
    { key: '/tasks', code: 'W-1.1', label: 'Задания на ДО', icon: <UnorderedListOutlined /> },
    { key: '/templates', code: 'W-1.3', label: 'Шаблоны заданий', icon: <BookOutlined /> },
    { key: '/results', code: 'W-2.1', label: 'Результаты ДО', icon: <FileDoneOutlined /> },
    { key: '/hs', code: 'W-2.5', label: 'Результаты ДО (хозспособ)', icon: <EditOutlined /> },
  ] },
  { group: 'Технические отчёты', items: [
    { key: '/reports', code: 'W-2.3', label: 'Реестр ТО', icon: <FileTextOutlined /> },
  ] },
  { group: 'Хранилище ТС', items: [
    { key: '/hierarchy', code: 'W-3.1', label: 'Иерархия оборудования', icon: <ClusterOutlined /> },
    { key: '/ts-records', code: 'W-3.4', label: 'Записи о ТС', icon: <ProfileOutlined /> },
    { key: '/logs', code: 'W-3.6', label: 'Лог загрузки данных', icon: <HistoryOutlined /> },
  ] },
  { group: 'Планирование и аналитика', items: [
    { key: '/planning', code: 'W-3.7', label: 'Подготовка к планированию', icon: <SlidersOutlined />, show: () => app.can('plan') || app.can('survey') || app.can('analytics') },
    { key: '/surveys', code: 'W-3.8', label: 'Опросные листы и расхождения', icon: <FormOutlined />, show: () => app.can('survey') || app.can('plan') || app.can('ts.confirm') },
    { key: '/analytics', code: 'W-4.1', label: 'Аналитика ДТОиР', icon: <BarChartOutlined />, show: () => app.can('analytics') },
    { key: '/dashboards', code: 'W-4.2', label: 'Дашборды', icon: <AppstoreOutlined /> },
  ] },
  { group: 'Входящие интеграции', items: [
    { key: '/inbound/plan', code: 'W-8.1', label: 'Загрузка пообъектного плана', icon: <CloudDownloadOutlined />, show: () => app.can('int.load') || app.hasRole('BDTS.VIEWER', 'BDTS.ADMIN') },
    { key: '/inbound/objects', code: 'W-8.2', label: 'Объекты X/Y/Z', icon: <EnvironmentOutlined />, show: () => app.can('int.load') || app.hasRole('BDTS.VIEWER', 'BDTS.ADMIN') },
  ] },
  { group: 'НСИ, ВТД, настройки', items: [
    { key: '/nsi/B306', code: 'W-5.1', label: 'НСИ: Б304–Б315', icon: <DatabaseOutlined /> },
    { key: '/dict38', code: 'W-5.10', label: 'Справочники ТО v3.8', icon: <SnippetsOutlined /> },
    { key: '/vtd', code: 'W-6.1', label: 'Участки ВТД', icon: <NodeIndexOutlined /> },
    { key: '/settings', code: 'W-7.1', label: 'Настройки модуля', icon: <SettingOutlined />, show: () => app.can('settings') || app.hasRole('BDTS.ADMIN') },
  ] },
];
const ALL_ITEMS = NAV.flatMap((g) => g.items);

const TITLES: [RegExp, string, string][] = [
  [/^\/cabinet/, 'W-0.4', 'Личный кабинет'], [/^\/profile/, 'W-0.1', 'Профиль и сессия'], [/^\/search/, 'W-0.2', 'Поиск объектов'],
  [/^\/tasks\/\d+/, 'W-1.2', 'Карточка задания на ДО'], [/^\/tasks/, 'W-1.1', 'Задания на ДО'], [/^\/templates\/\d+/, 'W-1.4', 'Карточка шаблона'],
  [/^\/templates/, 'W-1.3', 'Шаблоны заданий на ДО'], [/^\/results\/\d+/, 'W-2.2', 'Карточка результата ДО'], [/^\/results/, 'W-2.1', 'Результаты ДО'],
  [/^\/hs/, 'W-2.5', 'Результаты ДО хозяйственным способом'], [/^\/reports\/\d+/, 'W-2.4', 'Карточка технического отчёта'], [/^\/reports/, 'W-2.3', 'Реестр технических отчётов'],
  [/^\/hierarchy/, 'W-3.1', 'Иерархия оборудования'], [/^\/tm\//, 'W-3.2', 'Карточка технического места'], [/^\/eo\//, 'W-3.3', 'Карточка единицы оборудования'],
  [/^\/ts-records\/\d+/, 'W-3.5', 'Запись о техническом состоянии'], [/^\/ts-records/, 'W-3.4', 'Реестр записей о ТС'], [/^\/logs/, 'W-3.6', 'Лог и лог загрузки данных'],
  [/^\/planning/, 'W-3.7', 'Подготовка к планированию'], [/^\/surveys/, 'W-3.8', 'Опросные листы и расхождения'], [/^\/analytics/, 'W-4.1', 'Аналитика'],
  [/^\/dashboards/, 'W-4.2', 'Дашборды по ролям'], [/^\/nsi/, 'W-5.x', 'НСИ'], [/^\/dict38/, 'W-5.10', 'Справочники модели ТО v3.8'],
  [/^\/vtd\/\d+/, 'W-6.2', 'Карточка участка ВТД'], [/^\/vtd/, 'W-6.1', 'Реестр участков ВТД'], [/^\/settings/, 'W-7.1', 'Настройки модуля'],
  [/^\/inbound\/plan/, 'W-8.1', 'Загрузка пообъектного плана'], [/^\/inbound\/objects\/\d+/, 'W-8.3', 'Объект и ЕО из БДО'], [/^\/inbound\/objects/, 'W-8.2', 'Объекты X/Y/Z'],
];

/** Ошибка рендера экрана не должна давать пустую страницу: сообщение и повтор; сброс при переходе на другой адрес. */
class ScreenBoundary extends React.Component<{ resetKey: string; children: React.ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidUpdate(prev: { resetKey: string }) { if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null }); }
  componentDidCatch(error: Error) { console.error('Ошибка экрана', error); }
  render() {
    if (!this.state.error) return this.props.children;
    return <Result status="warning" title="Экран не удалось отобразить" subTitle={this.state.error.message}
      extra={<Button type="primary" onClick={() => this.setState({ error: null })}>Повторить</Button>} />;
  }
}

const Bell = observer(() => {
  const nav = useNavigate();
  const [filter, setFilter] = useState('Все');
  useEffect(() => { const t = setInterval(() => app.loadNotes(), 30000); return () => clearInterval(t); }, []);
  const items = app.notes.filter((n) => filter === 'Все' || (filter === 'Непрочитанные' ? !n.read : n.read));
  const content = (
    <div style={{ width: 480, maxWidth: '86vw' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, gap: 8, flexWrap: 'wrap' }}>
        <Segmented size="small" value={filter} onChange={(v) => setFilter(v as string)}
          options={[{ value: 'Все', label: `Все (${app.notes.length})` }, { value: 'Непрочитанные', label: `Непрочитанные (${app.unread})` },
            { value: 'Прочитанные', label: `Прочитанные (${app.notes.length - app.unread})` }]} />
        <Button size="small" type="link" disabled={!app.unread} onClick={() => app.readAll()}>Прочитать все</Button>
      </div>
      <div style={{ maxHeight: 420, overflowY: 'auto' }}>
        {items.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={filter === 'Все' ? 'Уведомлений нет' : `${filter} уведомления отсутствуют`} />}
        {items.map((n) => (
          <div key={n.id} style={{ padding: '8px 6px', borderBottom: '1px solid #EEF1F4', background: n.read ? undefined : '#F4F8FD' }}>
            <div style={{ display: 'flex', gap: 6, alignItems: 'flex-start' }}>
              <Tag color={n.type === 'Предупреждение' ? 'orange' : n.type === 'Ошибка' ? 'red' : 'blue'} style={{ marginTop: 2 }}>{n.type}</Tag>
              <a style={{ flex: 1, fontWeight: n.read ? 400 : 600, color: '#1B1F24' }} onClick={() => { app.markNote(n.id, { read: true }); if (n.link) nav(n.link); }}>{n.title}</a>
              {!n.read && <Badge status="processing" text={<span style={{ fontSize: 12, color: '#1F5FAD' }}>Новое</span>} />}
              <Tooltip title={n.flagged ? 'Снять пометку' : 'Пометить'}><StarFilled style={{ color: n.flagged ? '#B54708' : '#C7CED8', cursor: 'pointer' }} onClick={() => app.markNote(n.id, { flagged: !n.flagged })} /></Tooltip>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', color: '#5A6472', fontSize: 12, marginTop: 2 }}>
              <span>{n.detail} · {n.role}</span>
              <span style={{ whiteSpace: 'nowrap', marginLeft: 8 }}>{fmtDateTime(n.date)} · <a onClick={() => app.markNote(n.id, { read: !n.read })}>{n.read ? 'Отметить непрочитанным' : 'Отметить прочитанным'}</a></span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
  return (
    <Popover content={content} title="Уведомления" trigger="click" placement="rightBottom" onOpenChange={(o) => o && app.loadNotes()}>
      <Badge count={app.unread} size="small"><Button type="text" icon={<MessageOutlined />} aria-label={`Уведомления: непрочитанных ${app.unread}`} /></Badge>
    </Popover>
  );
});

const Shell = observer(() => {
  const loc = useLocation();
  const nav = useNavigate();
  const me = app.me!;
  const visible = NAV.map((g) => ({ ...g, items: g.items.filter((i) => (!i.show || i.show())) })).filter((g) => g.items.length);
  const active = ALL_ITEMS.filter((i) => loc.pathname.startsWith(i.key.replace(/\/B306$/, ''))).sort((a, b) => b.key.length - a.key.length)[0];
  const t = TITLES.find(([re]) => re.test(loc.pathname));
  useEffect(() => { if (t) app.visit({ key: loc.pathname, path: loc.pathname + loc.search, code: t[1], title: t[2] }); }, [loc.pathname, loc.search]);
  const prev = app.visits.filter((v) => v.key !== loc.pathname).slice(-2);
  const menuItems: any[] = visible.map((g) => ({
    type: 'group', key: g.group, label: app.collapsed ? null : g.group,
    children: g.items.map((i) => ({ key: i.key, icon: i.icon, label: <span>{app.techMode && <span className="mono" style={{ opacity: 0.6, marginRight: 6 }}>{i.code}</span>}{i.label}</span> })),
  }));
  const userMenu = {
    items: [
      { key: 'profile', icon: <UserOutlined />, label: <Link to="/profile">Профиль и роли</Link> },
      { key: 'tech', label: <Space onClick={(e) => e.stopPropagation()}><Switch size="small" checked={app.techMode} onChange={() => app.toggleTech()} /> Коды экранов и правил</Space> },
      { type: 'divider' as const },
      { key: 'switch', icon: <AuditOutlined />, label: 'Сменить пользователя', onClick: () => logout() },
      { key: 'out', icon: <LogoutOutlined />, label: 'Выйти', onClick: () => logout() },
    ],
  };
  return (
    <>
      <div className="app-body">
        <aside className={`app-side${app.collapsed ? ' collapsed' : ''}`} style={{ width: app.collapsed ? 80 : 240 }}>
          <div className="side-menu">
            <Menu mode="inline" inlineCollapsed={app.collapsed} selectedKeys={active ? [active.key] : []} items={menuItems} onClick={(e) => nav(e.key)} />
          </div>
          <div className="side-foot">
            <Dropdown menu={userMenu} trigger={['click']} placement="topLeft">
              <Button type="text" icon={<UserOutlined />} title={me.fio} aria-label={`Профиль пользователя: ${me.fio}`} />
            </Dropdown>
            <Bell />
            <Button type="text" icon={app.collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />} onClick={() => app.toggleCollapsed()} aria-label={app.collapsed ? 'Развернуть меню' : 'Свернуть меню'} />
          </div>
        </aside>
        <main className="app-main">
          <div className="crumbs">
            <nav aria-label="Последние разделы">
              {prev.map((v) => <Link key={v.key} to={v.path}><Tag style={{ cursor: 'pointer' }}>{app.techMode ? `${v.code}. ` : ''}{v.title}</Tag></Link>)}
              {t && <Tag color="purple" aria-current="page">{app.techMode ? `${t[1]}. ` : ''}{t[2]}</Tag>}
            </nav>
            {me.deo && <Tag color="orange">Данные ограничены по ДЭО: {me.deo}</Tag>}
          </div>
          <ScreenBoundary resetKey={loc.pathname}>
          <Suspense fallback={<div style={{ padding: 40, textAlign: 'center' }}><Spin /></div>}>
            <Routes>
              <Route path="/" element={<Navigate to={me.startRoute} replace />} />
              <Route path="/auth-callback" element={<Navigate to={me.startRoute} replace />} />
              <Route path="/cabinet" element={<pages.Cabinet />} />
              <Route path="/profile" element={<pages.Profile />} />
              <Route path="/search" element={<pages.Search />} />
              <Route path="/tasks" element={<pages.Tasks />} />
              <Route path="/tasks/:id" element={<pages.TaskCard />} />
              <Route path="/templates" element={<pages.Templates />} />
              <Route path="/templates/:id" element={<pages.TemplateCard />} />
              <Route path="/results" element={<pages.Results />} />
              <Route path="/hs" element={<pages.Results hs />} />
              <Route path="/results/:id" element={<pages.ResultCard />} />
              <Route path="/reports" element={<pages.Reports />} />
              <Route path="/reports/:id" element={<pages.ReportCard />} />
              <Route path="/hierarchy" element={<pages.Hierarchy />} />
              <Route path="/tm/:id" element={<pages.TmCard />} />
              <Route path="/eo/:id" element={<pages.EoCard />} />
              <Route path="/ts-records" element={<pages.TsRecords />} />
              <Route path="/ts-records/:id" element={<pages.TsRecordCard />} />
              <Route path="/logs" element={<pages.Logs />} />
              <Route path="/planning" element={<pages.Planning />} />
              <Route path="/surveys" element={<pages.Surveys />} />
              <Route path="/analytics" element={<pages.Analytics />} />
              <Route path="/dashboards" element={<pages.Dashboards />} />
              <Route path="/nsi/:code" element={<pages.Nsi />} />
              <Route path="/dict38" element={<pages.Dict38 />} />
              <Route path="/vtd" element={<pages.Vtd />} />
              <Route path="/vtd/:id" element={<pages.VtdCard />} />
              <Route path="/settings" element={<pages.Settings />} />
              <Route path="/inbound/plan" element={<pages.PlanLoad />} />
              <Route path="/inbound/objects" element={<pages.Objects />} />
              <Route path="/inbound/objects/:id" element={<pages.ObjectCard />} />
              <Route path="*" element={<Result status="404" title="Экран не найден" extra={<Link to="/">На стартовый экран</Link>} />} />
            </Routes>
          </Suspense>
          </ScreenBoundary>
        </main>
      </div>
    </>
  );
});

const App = observer(() => {
  const [err, setErr] = useState('');
  useEffect(() => { app.load().catch((e) => setErr(e?.detail || 'Не удалось загрузить профиль пользователя')); }, []);
  if (err) return <Result status="warning" title="Модуль недоступен" subTitle={err} extra={<Button type="primary" onClick={() => relogin()}>Войти заново</Button>} />;
  if (!app.me || !app.refs) return <div style={{ padding: 60, textAlign: 'center' }}><Spin tip="Загрузка профиля…" /></div>;
  if (!app.me.roles.length) return <Result status="403" title="Нет ролей МП-3.5" subTitle="У учётной записи нет функциональных ролей модуля БДТС. Обратитесь к администратору." extra={<Button onClick={() => logout()}>Выйти</Button>} />;
  return <Shell />;
});

export default App;
