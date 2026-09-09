# Meridian — Prospecting Desk (Flask)

Flask-приложение, собранное по макетам `*.dc.html`: витрина событий-триггеров,
поиск проспектов, досье и конфигурация источников для private-wealth деска.

Сейчас данные берутся из **in-memory заглушек** (перенесены один-в-один из макетов).
Весь доступ к данным идёт через репозитории, поэтому подключение реальных БД
и интеграций не затронет ни шаблоны, ни API.

## Запуск

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

flask --app wsgi run --debug          # http://127.0.0.1:5000
# или
gunicorn -w 4 -b 0.0.0.0:8000 wsgi:app
```

Тесты:

```bash
pytest -q
```

## Структура

```
app/
  __init__.py            application factory, error handlers, глобалы шаблонов
  config.py              конфиг из окружения (DATABASE_URL, REDIS_URL, ... — заготовки)
  models.py              доменные dataclass-модели + to_dict()
  repositories/
    base.py              протоколы репозиториев — контракт для любой реализации
    memory.py            текущая in-memory реализация
    seed_data.py         демо-данные из макетов
    __init__.py          выбор бэкенда по REPOSITORY_BACKEND
  services/desk.py       сборка вью-моделей (страницы и API используют один сервис)
  blueprints/
    web/routes.py        HTML-страницы
    api/routes.py        JSON API (/api/v1)
  templates/             base + partials (sidebar, header) + pages
  static/css/app.css     стили, перенесённые из макетов
tests/test_app.py        smoke-тесты страниц, действий и API
wsgi.py                  точка входа
```

## Страницы

| URL | Экран макета |
|---|---|
| `/` | `index.dc.html` — Desk. Раскладки `?variant=desk\|queue\|command` |
| `/prospects` | `prospectbrief.dc.html` — поиск и список проспектов |
| `/prospects/<id>` | `prospectdetail.dc.html` — досье |
| `/triggers` | `triggers.dc.html` — лента триггеров, фильтр, раскрытие строки, пагинация |
| `/sources` | `sources.dc.html` — категории, источники, лог ингеста |
| `/healthz` | health-check |

Интерактив макета (`setState`) переведён на серверный стейт: раскладка,
категория, look-back, раскрытая строка — в query-параметрах; переключение
watchlist, задач и категорий — POST-формы.

## API

```
GET  /api/v1/health
GET  /api/v1/triggers?category=&page=&per_page=
GET  /api/v1/triggers/<id>
GET  /api/v1/prospects?q=
GET  /api/v1/prospects/queue
GET  /api/v1/prospects/<id>              # проспект + досье
POST /api/v1/prospects/<id>/watch        # {"watched": true}
GET  /api/v1/desk/overview
GET  /api/v1/desk/tasks
POST /api/v1/desk/tasks/<id>/toggle
GET  /api/v1/desk/watchlist
GET  /api/v1/sources
GET  /api/v1/sources/categories
POST /api/v1/sources/categories/<key>/toggle
GET  /api/v1/sources/logs
```

## Как подключить реальную БД

1. Заполнить `DATABASE_URL` в `.env`.
2. Добавить `app/repositories/sql.py` с классами, реализующими протоколы из
   `app/repositories/base.py` (сигнатуры уже зафиксированы).
3. В `app/repositories/__init__.py` добавить ветку `backend == "sql"`.
4. Переключить `REPOSITORY_BACKEND=sql`.

Шаблоны, сервисы и API менять не нужно.
