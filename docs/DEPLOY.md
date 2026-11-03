# Развёртывание

Версия: см. `VERSION`. Все сервисы — открытое ПО в Docker Compose; образы приложения собираются на сервере из исходников.

## Требования к серверу

- Linux x86-64 (проверено на Ubuntu 24.04), от 4 CPU / 4 ГБ RAM (+ swap 4 ГБ), диск от 20 ГБ.
- Docker Engine 24+ с плагином Compose (официальный репозиторий download.docker.com), `git`, `openssl`.
- DNS: A-запись домена указывает на сервер; открыты порты 80 и 443 (Caddy сам получает сертификат Let's Encrypt).

## Первый запуск из репозитория

```bash
git clone <URL репозитория> /opt/bdts-mvp
cd /opt/bdts-mvp
sh scripts/init-env.sh          # .env со случайными паролями (chmod 600); существующий .env не перезаписывается
nano .env                       # PRIMARY_HOST, PUBLIC_IP, SITE_HOSTS, PUBLIC_URLS, OIDC_ISSUERS — под ваш домен
docker compose up -d --build    # postgres, redis, rabbitmq, s3, keycloak, migrate, api, worker, web, caddy
docker compose ps
```

`migrate` выполняет `alembic upgrade head` и загружает демо-данные в пустую БД, затем стартуют `api` и `worker`.
Keycloak при первом старте импортирует realm `bdts` (роли, группы, демо-пользователи с паролем `DEMO_PASSWORD` из `.env`).

### Другой домен

Адреса задаются в `.env`:

| Переменная | Пример | Назначение |
| --- | --- | --- |
| `PRIMARY_HOST` | `arm.example.ru` | Основное имя; на него перенаправляется доступ по IP |
| `PUBLIC_IP` | `203.0.113.10` | IP сервера для перенаправления `http://IP` → `https://PRIMARY_HOST` |
| `SITE_HOSTS` | `arm.example.ru` | Имена, на которых Caddy обслуживает сайт (через запятую) |
| `PUBLIC_URLS` | `https://arm.example.ru` | Разрешённые адреса веб-клиента (CORS) |
| `OIDC_ISSUERS` | `https://arm.example.ru/auth/realms/bdts` | Допустимые издатели токенов Keycloak |

Разрешённые redirect URI клиента `bdts-web` хранятся в `infra/keycloak/realm-bdts.json`. Для нового домена пересоздайте файл
до первого запуска (нужен Python 3.12): `PUBLIC_URLS=https://arm.example.ru python infra/keycloak/gen_realm.py`.
Если Keycloak уже запущен, адреса меняются в консоли администратора (`/auth/admin`, клиент `bdts-web`) либо сбросом данных (ниже).

## Адреса

| Что | Адрес |
| --- | --- |
| Приложение | `https://<PRIMARY_HOST>` |
| OpenAPI | `https://<PRIMARY_HOST>/api/docs` |
| Проверка готовности / версия | `/api/ready`, `/api/health` |
| Администрирование Keycloak | `https://<PRIMARY_HOST>/auth/admin` (учётка `KEYCLOAK_ADMIN` из `.env`) |

HTTP-доступ по IP перенаправляется на HTTPS-имя: вход OIDC с PKCE требует защищённого контекста браузера.

Тестовый стенд: https://stand1.geometry-dev.ru, ВМ Ubuntu 24.04, 2 CPU / 4 ГБ + swap 4 ГБ, каталог `/opt/bdts-mvp`.

## Обновление

```bash
cd /opt/bdts-mvp && git pull && docker compose up -d --build api worker web migrate
```

Сброс демо-данных (удаляет БД и файлы, Keycloak переимпортирует realm):

```bash
docker compose down && docker volume rm bdts_pgdata bdts_s3data bdts_rabbitdata && docker compose up -d
```

## Ресурсы

Пиковое потребление стенда ≈ 2 ГБ RAM: Keycloak ~500 МБ, API ~260 МБ, RabbitMQ ~140 МБ, остальное < 100 МБ на сервис.
Лимиты памяти заданы в `docker-compose.yml`.
