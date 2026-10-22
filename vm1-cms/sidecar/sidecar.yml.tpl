# Конфигурация Graylog Sidecar (значения подставляются из переменных окружения при старте контейнера)

# адрес REST API Graylog и токен доступа
server_url: "${GRAYLOG_API_URL}"
server_api_token: "${SIDECAR_API_TOKEN}"

# идентификатор и имя, под которыми Sidecar виден в Graylog
node_id: "lab-cms-sidecar"
node_name: "${SIDECAR_NODE_NAME}"

# как часто Sidecar опрашивает Graylog на предмет новой конфигурации (секунды)
update_interval: 10
tls_skip_verify: false
# отправлять в Graylog статус (нагрузка, список логов)
send_status: true

# каталоги, содержимое которых показывается в веб-интерфейсе при выборе файлов
list_log_files:
  - /var/log/lab-nginx
  - /var/log/php-fpm
  - /var/log/mysql

cache_path: /var/cache/graylog-sidecar
log_path: /var/log/graylog-sidecar
log_rotate_max_file_size: 10MiB
log_rotate_keep_files: 10

# куда Sidecar пишет сгенерированные конфигурации коллекторов
collector_configuration_directory: /var/lib/graylog-sidecar/generated

# какие исполняемые файлы Sidecar вправе запускать
# путь /usr/lib/graylog-sidecar/filebeat использует стандартный коллектор "filebeat on Linux" в Graylog
collector_binaries_accesslist:
  - /usr/lib/graylog-sidecar/filebeat
  - /usr/share/filebeat/bin/filebeat
