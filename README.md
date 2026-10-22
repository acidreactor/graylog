# Graylog: сбор логов через Sidecar и разделение по стримам

Две ВМ в виде двух docker compose стеков:

| Стек | Роль | Компоненты |
|------|------|------------|
| `vm1-cms` | ВМ с CMS | WordPress (php-fpm), nginx, MySQL, Graylog Sidecar (с Filebeat) |
| `vm2-graylog` | ВМ с Graylog | Graylog, OpenSearch, MongoDB, Data Prepper |

```
vm1-cms                                         vm2-graylog
nginx / php-fpm / mysql                         Graylog (Beats input :5044) --> OpenSearch
        | файлы логов                              |  стримы: Nginx, PHP-FPM, MySQL      ^
   Sidecar --> Filebeat --- Beats :5044 ---------->+                                    |
      ^                                            |   MongoDB (настройки)       Data Prepper
      +----------- REST API :9000 (конфигурация) --+                             (копия индексов)
```

Sidecar не собирает логи сам: он получает от Graylog конфигурацию, запускает по ней Filebeat и следит за ним.
Конфигурация хранится в Graylog, поэтому состав собираемых логов меняется из веб-интерфейса без правки файлов на ВМ.

## Структура

```
vm1-cms/
  docker-compose.yml
  .env.example
  nginx/default.conf
  php-fpm/zzz-logs.conf
  mysql/lab.cnf
  sidecar/
    Dockerfile                # Graylog Sidecar и Filebeat
    entrypoint.sh
    sidecar.yml.tpl           # конфигурация Sidecar
    filebeat-template.yml     # конфигурация Filebeat для Graylog (вставляется в веб-интерфейс)
vm2-graylog/
  docker-compose.yml
  .env.example
  data-prepper/
    pipelines.yaml            # конфигурация Data Prepper
    data-prepper-config.yaml
  scripts/
    provision.py              # input, стримы и токен Sidecar через REST API
screenshots/
```

## Требования

- Docker с Compose v2
- около 5 ГБ свободной памяти и 6 ГБ на диске под образы
- на Linux-хосте: `sudo sysctl -w vm.max_map_count=262144`
- стенды предыдущих работ нужно остановить (порты 8080, 9000, 9200, 5044)

## Запуск

Общая сеть:

```bash
docker network create lab4-net
```

Вторая ВМ (Graylog и всё, что с ним связано):

```bash
cd vm2-graylog
cp .env.example .env
docker compose up -d
```

Graylog стартует 1-2 минуты. Контейнер `provision` дожидается его, создаёт Beats input,
три стрима и токен для Sidecar и печатает токен в лог:

```bash
docker compose logs provision | grep SIDECAR_API_TOKEN
```

Первая ВМ (токен вставляется в `.env`):

```bash
cd ../vm1-cms
cp .env.example .env
# в .env записать SIDECAR_API_TOKEN=<токен из лога provision>
docker compose up -d --build
```

Веб-интерфейс Graylog: http://localhost:9000, логин `admin`, пароль `admin` (меняется в `.env`).
WordPress: http://localhost:8080.

## Подключение Sidecar и настройка сбора логов

После запуска Sidecar появляется в Graylog: System → Sidecars → Overview, узел `vm1-cms`.
Сбор логов задаётся в веб-интерфейсе:

1. System → Sidecars → Configuration → Create Configuration.
2. Name: `lab-cms`, Collector: `filebeat on Linux`.
3. Вставить содержимое `vm1-cms/sidecar/filebeat-template.yml` и сохранить.
4. System → Sidecars → Administration → выбрать узел `vm1-cms` → Process → Assign Configuration → `lab-cms` → Apply.

Через несколько секунд Sidecar получает конфигурацию, запускает Filebeat, и логи начинают поступать в Graylog.

## Что настроено

### Sidecar

`vm1-cms/sidecar/sidecar.yml.tpl`: адрес API и токен Graylog, идентификатор узла, период опроса,
список разрешённых исполняемых файлов (`collector_binaries_accesslist`). Образ собирается из `Dockerfile`:
пакет `graylog-sidecar` из репозитория Graylog и Filebeat.

### Конфигурация Filebeat

`vm1-cms/sidecar/filebeat-template.yml` собирает шесть файлов логов: access и error nginx и php-fpm,
error и slow log MySQL (multiline). Каждому источнику добавляется поле `service` (`nginx`, `php-fpm`, `mysql`)
и `log_type`; отправка идёт в Beats input Graylog.

### Стримы

`vm2-graylog/scripts/provision.py` создаёт стримы **Nginx**, **PHP-FPM**, **MySQL**.
В каждом два правила, достаточно любого (`OR`):

- поле `service` равно имени сервиса;
- путь к файлу лога (`log_file_path`) соответствует регулярному выражению.

Опция `remove_matches_from_default_stream` убирает сообщения из общего потока Default Stream,
поэтому каждый лог виден ровно в одном стриме.

### Data Prepper

`vm2-graylog/data-prepper/pipelines.yaml`: источник `opensearch` читает индексы Graylog (`graylog_N`),
`add_entries` добавляет поле `copied_by`, sink `opensearch` записывает документы в индекс `lab-graylog-copy`.
Идентификатор документа берётся из источника, поэтому повторное чтение (раз в минуту) не создаёт дубликатов.
Копия не влияет на работу Graylog и его хранение.

Проверка:

```bash
curl -s 'localhost:9200/_cat/indices/lab-graylog-copy?v'
```

## Генерация данных

```bash
for i in $(seq 1 30); do curl -s -o /dev/null http://localhost:8080/; done
curl -s -o /dev/null http://localhost:8080/missing.php

cd vm1-cms
docker compose exec mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "SELECT SLEEP(2);"'
docker compose restart php-fpm mysql
```

## Проверка в Graylog

1. Streams: три стрима с ненулевым числом сообщений.
2. Откройте стрим (например Nginx): сообщения только nginx, поля `service`, `log_type`, `message`, `source`.
3. Search с фильтром `service:mysql AND log_type:slowlog`.
4. System → Sidecars: статус узла `Running`.

Скриншоты лежат в каталоге `screenshots/`.

## Запуск на отдельных ВМ

- в `vm1-cms/.env`: `GRAYLOG_API_URL=http://<IP второй ВМ>:9000/api/`;
- в `vm2-graylog/.env`: `GRAYLOG_EXTERNAL_URI=http://<IP второй ВМ>:9000/`;
- в шаблоне Filebeat заменить `hosts: ["graylog:5044"]` на `<IP второй ВМ>:5044`;
- убрать секции `networks` из compose-файлов.

## Примечания

- Безопасность OpenSearch отключена, Graylog и Sidecar работают по HTTP: это учебный стенд.
- Пароль и секрет в `.env.example` учебные.

