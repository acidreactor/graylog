#!/bin/sh
set -e

if [ -z "$SIDECAR_API_TOKEN" ]; then
  echo "SIDECAR_API_TOKEN is empty: take the token from the provision container logs on the Graylog VM" >&2
  exit 1
fi

# sidecar обращается к Graylog напрямую, прокси из окружения сбрасываем
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY no_proxy NO_PROXY ALL_PROXY all_proxy

# значения из переменных окружения подставляются в шаблон конфигурации
envsubst < /etc/graylog/sidecar/sidecar.yml.tpl > /etc/graylog/sidecar/sidecar.yml

exec graylog-sidecar -c /etc/graylog/sidecar/sidecar.yml
