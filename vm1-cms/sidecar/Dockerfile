ARG FILEBEAT_VERSION=8.15.3

# Filebeat берётся из официального образа Elastic (бинарник копируется ниже)
FROM docker.elastic.co/beats/filebeat:${FILEBEAT_VERSION} AS filebeat

FROM debian:12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg gettext-base procps \
 && rm -rf /var/lib/apt/lists/*

# Graylog Sidecar из официального репозитория Graylog
RUN curl -fsSL -o /tmp/graylog-sidecar-repository.deb \
      https://packages.graylog2.org/repo/packages/graylog-sidecar-repository_1-5_all.deb \
 && dpkg -i /tmp/graylog-sidecar-repository.deb \
 && apt-get update \
 && apt-get install -y --no-install-recommends graylog-sidecar \
 && rm -rf /var/lib/apt/lists/* /tmp/*.deb

# Filebeat - коллектор, которым управляет Sidecar (путь совпадает с путём пакета: /usr/share/filebeat/bin/filebeat)
COPY --from=filebeat /usr/share/filebeat/filebeat /usr/share/filebeat/bin/filebeat

# Graylog запускает Filebeat по пути /usr/lib/graylog-sidecar/filebeat:
# если пакет Sidecar его не принёс, подставляется ссылка на бинарник выше
RUN mkdir -p /usr/lib/graylog-sidecar \
 && { [ -e /usr/lib/graylog-sidecar/filebeat ] || ln -s /usr/share/filebeat/bin/filebeat /usr/lib/graylog-sidecar/filebeat; }

COPY sidecar.yml.tpl /etc/graylog/sidecar/sidecar.yml.tpl
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
