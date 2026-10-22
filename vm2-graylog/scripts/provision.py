#!/usr/bin/env python3
"""Настройка Graylog через REST API.

Создаёт Beats input, три стрима (Nginx, PHP-FPM, MySQL) и токен для Sidecar.
Скрипт можно запускать повторно: уже существующие input и стримы не создаются заново.
Только стандартная библиотека Python, внешние пакеты не нужны.
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = os.environ.get("GRAYLOG_API", "http://graylog:9000/api").rstrip("/")
USER = os.environ.get("GRAYLOG_USER", "admin")
PASSWORD = os.environ.get("GRAYLOG_PASSWORD", "admin")
AUTH = "Basic " + base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()

# запросы к Graylog идут напрямую, переменные окружения HTTP_PROXY игнорируются
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def call(method, path, body=None, auth=True):
    """Возвращает (код ответа, разобранный JSON или None)."""
    data = None
    headers = {"Accept": "application/json", "X-Requested-By": "provision"}
    if auth:
        headers["Authorization"] = AUTH
    if method != "GET":
        data = json.dumps(body if body is not None else {}).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with OPENER.open(req, timeout=30) as resp:
            raw = resp.read()
            code = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read()
        code = e.code
    except (urllib.error.URLError, OSError):
        return 0, None
    try:
        return code, json.loads(raw) if raw else None
    except ValueError:
        return code, None


def wait_for_graylog():
    print("== ожидание Graylog", flush=True)
    unauthorized = 0
    for _ in range(120):
        code, info = call("GET", "/system")
        if code == 200 and info and info.get("version"):
            print(f"Graylog готов: {info['version']}", flush=True)
            return
        if code == 401:
            unauthorized += 1
            if unauthorized >= 6:
                sys.exit("Graylog отвечает 401: проверьте GRAYLOG_ADMIN_PASSWORD в .env "
                         "(он должен совпадать с паролем, для которого задан GRAYLOG_ROOT_PASSWORD_SHA2)")
        else:
            unauthorized = 0
        time.sleep(5)
    sys.exit("Graylog не ответил за 10 минут")


def create_input():
    print("== Beats input (порт 5044)", flush=True)
    _, inputs = call("GET", "/system/inputs")
    for item in (inputs or {}).get("inputs", []):
        if item.get("title") == "Beats (Sidecar)":
            print(f"input уже существует: {item.get('id')}")
            return
    code, resp = call("POST", "/system/inputs", {
        "title": "Beats (Sidecar)",
        "type": "org.graylog.plugins.beats.Beats2Input",
        "global": True,
        "configuration": {
            "bind_address": "0.0.0.0",
            "port": 5044,
            "recv_buffer_size": 1048576,
            "tcp_keepalive": False,
            "use_null_delimiter": True,
            "tls_enable": False,
            "number_worker_threads": 2,
            "no_beats_prefix": False,
        },
    })
    print(f"input создан (HTTP {code}): {resp}")


def default_index_set():
    _, resp = call("GET", "/system/indices/index_sets")
    for item in (resp or {}).get("index_sets", []):
        if item.get("default"):
            return item["id"]
    sys.exit("не найден index set по умолчанию")


def make_stream(index_set, title, description, service, path_regex):
    """Стрим с двумя правилами, достаточно любого (OR):
    1) поле service равно значению (его добавляет Filebeat);
    2) путь файла лога (log_file_path) подходит под регулярное выражение."""
    _, resp = call("GET", "/streams")
    for item in (resp or {}).get("streams", []):
        if item.get("title") == title:
            print(f"стрим {title} уже существует: {item.get('id')}")
            return
    code, resp = call("POST", "/streams", {
        "title": title,
        "description": description,
        "matching_type": "OR",
        "remove_matches_from_default_stream": True,
        "index_set_id": index_set,
        "rules": [
            {"field": "service", "type": 1, "value": service, "inverted": False},
            {"field": "log_file_path", "type": 2, "value": path_regex, "inverted": False},
        ],
    })
    stream_id = (resp or {}).get("stream_id")
    if not stream_id:
        print(f"не удалось создать стрим {title} (HTTP {code}): {resp}")
        return
    call("POST", f"/streams/{stream_id}/resume")
    print(f"стрим {title} создан и запущен: {stream_id}")


def create_token():
    print("== токен для Sidecar", flush=True)
    _, user = call("GET", "/users/admin")
    user_ids = [(user or {}).get("id"), "admin"]
    name = f"sidecar-{int(time.time())}"
    for uid in [u for u in user_ids if u]:
        code, resp = call("POST", f"/users/{uid}/tokens/{name}")
        if resp and resp.get("token"):
            return resp["token"]
    return None


def main():
    wait_for_graylog()
    create_input()

    print("== стримы", flush=True)
    index_set = default_index_set()
    make_stream(index_set, "Nginx", "Логи nginx", "nginx", ".*lab-nginx.*")
    make_stream(index_set, "PHP-FPM", "Логи php-fpm", "php-fpm", ".*php-fpm.*")
    make_stream(index_set, "MySQL", "Логи MySQL", "mysql", ".*/var/log/mysql/.*")

    token = create_token()
    print()
    if token:
        print("=" * 64)
        print(f"SIDECAR_API_TOKEN={token}")
        print("Скопируйте значение в vm1-cms/.env")
        print("=" * 64)
    else:
        print("Не удалось создать токен автоматически.")
        print("Создайте его вручную: System -> Sidecars или меню пользователя -> Edit tokens")
    print("provision завершён")


if __name__ == "__main__":
    main()
