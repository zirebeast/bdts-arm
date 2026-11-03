// W-0.1 Профиль пользователя и сессия: роли (Auth / Keycloak → LDAP), разрешённые действия, ограничение по ДЭО
import { Button, Space, Table, Tag } from 'antd';
import { observer } from 'mobx-react-lite';
import { authMode, logout } from '../auth';
import { app } from '../store';
import { Block, KV, ScreenTitle } from '../ui';

const Profile = observer(() => {
  const me = app.me!;
  return (
    <div>
      <ScreenTitle code="W-0.1" title="Профиль пользователя и сессия" extra={<Button onClick={() => logout()}>Выйти / сменить пользователя</Button>} />
      <Block title="Учётная запись"><KV cols={3} items={[['ФИО', me.fio], ['Логин', <span className="mono">{me.username}</span>], ['Должность', me.position || '—'],
        ['Ограничение данных по ДЭО', me.deo || 'Нет (все ДЭО)'], ['Аутентификация', authMode() === 'keycloak' ? 'Keycloak OIDC (единый вход ЕЦП, LDAP-федерация)' : 'Режим разработки (dev)'], ['Стартовый экран', me.startRoute]]} /></Block>
      <Block title="Бизнес-роли МП-3.5">
        <Table size="small" rowKey="code" pagination={false} dataSource={me.roles} columns={[{ title: 'Роль', dataIndex: 'label' }, { title: 'Техническое имя', dataIndex: 'code', render: (v) => <span className="mono">{v}</span> },
          { title: 'Тип', dataIndex: 'delta', render: (d) => (d ? <Tag color="purple">ТПР v9.3+</Tag> : <Tag>ТПР v9.3</Tag>) }]} />
      </Block>
      <Block title="Разрешённые действия (кнопки показываются только для допустимых статуса и роли)">
        <Space wrap>{me.actions.map((a) => <Tag key={a} className="mono">{a}</Tag>)}{!me.actions.length && <span className="hint">Только просмотр</span>}</Space>
      </Block>
    </div>
  );
});

export default Profile;
