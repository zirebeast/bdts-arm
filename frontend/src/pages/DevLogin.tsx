// Вход в dev-режиме (без Keycloak): выбор демо-пользователя. В контуре используется Keycloak (authMode=keycloak).
import { Button, Card, List, Typography } from 'antd';
import { DEV_USERS, devLogin } from '../auth';

export default function DevLogin() {
  return (
    <div className="login-wrap">
      <Card style={{ width: 460, maxWidth: '100%' }} title="МП-3.5 «БДТС» — вход (режим разработки)">
        <Typography.Paragraph type="secondary">Выберите демо-пользователя. Роли и ограничение по ДЭО соответствуют ролевой модели ТПР.</Typography.Paragraph>
        <List size="small" dataSource={DEV_USERS} renderItem={([login, label]) => (
          <List.Item actions={[<Button key="in" type="primary" size="small" onClick={() => devLogin(login)}>Войти</Button>]}>
            <span className="mono">{login}</span>&nbsp;— {label}
          </List.Item>
        )} />
      </Card>
    </div>
  );
}
