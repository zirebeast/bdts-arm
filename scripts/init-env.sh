#!/usr/bin/env sh
# Создать .env со случайными секретами (однократно, на сервере). Существующий .env не перезаписывается.
set -e
cd "$(dirname "$0")/.."
[ -f .env ] && { echo ".env уже существует"; exit 0; }
rnd() { openssl rand -base64 24 | tr -d '/+=' | cut -c1-20; }
sed -e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(rnd)/" \
    -e "s/^RABBITMQ_PASSWORD=.*/RABBITMQ_PASSWORD=$(rnd)/" \
    -e "s/^S3_SECRET_KEY=.*/S3_SECRET_KEY=$(rnd)/" \
    -e "s/^KEYCLOAK_ADMIN_PASSWORD=.*/KEYCLOAK_ADMIN_PASSWORD=$(rnd)/" \
    -e "s/^DEMO_PASSWORD=.*/DEMO_PASSWORD=Bdts-$(openssl rand -hex 3)!/" \
    .env.example > .env
chmod 600 .env
echo ".env создан"
