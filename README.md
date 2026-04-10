# CLI Monitoring Tools

Набор CLI-утилит для работы с системами мониторинга и управления доменами. Все утилиты написаны на Python 3 и работают через API соответствующих сервисов.

## Структура

```
├── sentry_api_tools/      # Работа с Sentry
├── zabbix_api_tools/      # Работа с Zabbix
├── uptimekuma_tools/      # Работа с Uptime Kuma
└── domain_tools/          # Проверка сроков истечения доменов
```

## Sentry API Tools

Просмотр и управление issues в Sentry через API.

### viewer.py

Просмотр проектов и issues.

```bash
python viewer.py projects                                    # список проектов
python viewer.py issues --current --project myproject        # текущие issues
python viewer.py issues --duty-shift --project myproject     # issues за последние 12 часов
python viewer.py issues --duty-day --project myproject       # issues за последние 24 часа
python viewer.py issue 123456789                             # детали issue
python viewer.py issue 123456789 --stacktrace                # со стектрейсом
python viewer.py issue 123456789 --events 25                 # с последними событиями
```

### manager.py

Управление issues: resolve, ignore (snooze), assign.

```bash
python manager.py resolve 123456789                          # резолв issue
python manager.py resolve 123456789 --in-next-release        # резолв в следующем релизе
python manager.py ignore 123456789 --duration 480            # игнор на 480 минут
python manager.py ignore 123456789 --count 100               # игнор до 100 повторений
python manager.py assign 123456789 --to john@example.com     # назначить на пользователя
python manager.py assign 123456789 --to team:backend         # назначить на команду
```

**Переменные окружения:**
```
SENTRY_URL=https://sentry.example.com/
SENTRY_TOKEN=your_token_here
```

## Zabbix API Tools

Работа с проблемами, трендами и maintenance-окнами в Zabbix.

### problems_viewer.py

Просмотр текущих и исторических проблем.

```bash
python problems_viewer.py --current                          # активные проблемы
python problems_viewer.py --duty-shift                       # за последние 12 часов
python problems_viewer.py --duty-day                         # за последние 24 часа
python problems_viewer.py --duty-week                        # за последние 7 дней
python problems_viewer.py --duty-month                       # за последние 30 дней
python problems_viewer.py --duty-shift --hosts               # группировка по хостам
python problems_viewer.py --duty-day --problems              # группировка по проблемам
python problems_viewer.py --current --history                # с полной историей действий
```

### trends_viewer.py

Анализ роста нагрузки (CPU, memory, load average) по хостам за несколько периодов. Показывает top-N хостов с наибольшим ростом метрик.

```bash
python trends_viewer.py --mode week --count 4                # понедельное сравнение за 4 недели
python trends_viewer.py --mode month --count 3 --top 5       # помесячное, top-5 хостов
python trends_viewer.py --mode week --count 8 --output summary  # сводная таблица
python trends_viewer.py --mode month --count 6 --group "Linux servers"  # по группе хостов
```

### trouble_manager.py

Управление проблемами и maintenance-окнами.

```bash
# Проблемы
python trouble_manager.py --problem ack --event-id 1234               # подтвердить проблему
python trouble_manager.py --problem close --event-id 1234             # закрыть проблему
python trouble_manager.py --problem suppress --host web01             # подавить по хосту
python trouble_manager.py --problem severity --event-id 1234 --severity high  # изменить severity

# Maintenance
python trouble_manager.py --maintenance create --name "Deploy" --host web01 web02 --duration 60
python trouble_manager.py --maintenance list
python trouble_manager.py --maintenance delete --maintenance-id 12
```

**Переменные окружения:**
```
ZABBIX_URL=https://zabbix.example.com/api_jsonrpc.php
ZABBIX_TOKEN=your_token_here
```

## Uptime Kuma Tools

### viewer.py

Просмотр статуса мониторов и истории heartbeat-ов в Uptime Kuma.

```bash
python viewer.py --problems                                  # текущие DOWN-мониторы
python viewer.py --problems --duty-shift                     # мониторы с DOWN за 12 часов
python viewer.py --problems --duty-day                       # мониторы с DOWN за 24 часа
python viewer.py --history --id 5 --duty-shift               # история монитора по ID
python viewer.py --history --name "API" --duty-day           # история монитора по имени
```

**Переменные окружения:**
```
UPTIMEKUMA_URL=http://uptimekuma.example.com:3001
UPTIMEKUMA_USERNAME=admin
UPTIMEKUMA_PASSWORD=your_password_here
```

## Domain Tools

Проверка сроков истечения доменов.

### expiry_checker.py

Универсальная проверка через RDAP (с fallback на WHOIS). Не требует API-ключей.

```bash
python expiry_checker.py domains.txt                         # проверить список доменов
python expiry_checker.py domains.txt --warn 60               # предупреждать за 60 дней
python expiry_checker.py domains.txt --delay 2               # задержка между запросами
```

### godaddy_checker.py

Проверка доменов через GoDaddy API. Дополнительно определяет статус парковки и auto-renewal.

```bash
python godaddy_checker.py godaddy_domains.txt                # проверить из файла
python godaddy_checker.py godaddy_domains.txt --warn 60      # порог предупреждения
python godaddy_checker.py example.com example.org            # проверить конкретные домены
```

**Переменные окружения:**
```
GODADDY_API_KEY=your_key
GODADDY_API_SECRET=your_secret
```

## Установка

Каждая утилита имеет свой `requirements.txt`. Установка зависимостей:

```bash
pip install -r sentry_api_tools/requirements.txt
pip install -r zabbix_api_tools/requirements.txt
pip install -r uptimekuma_tools/requirements.txt
pip install -r domain_tools/requirements.txt
```

Переменные окружения задаются через `.env` файлы в директориях утилит или через `export`.

## Лицензия

Apache License 2.0
