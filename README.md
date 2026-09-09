# Meridian — Prospecting Desk (Flask)

Flask-приложение, собранное по макетам `*.dc.html`: витрина событий-триггеров,
поиск проспектов, досье и конфигурация источников для private-wealth деска.

Из Supabase читаются триггеры (`triggers`) и брифы (`researched_documents`);
Desk-виджеты пока на демо-данных. Источник переключается одной переменной
`REPOSITORY_BACKEND` (`memory` | `supabase`).

## Запуск

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # заполнить SUPABASE_URL и SUPABASE_SECRET_KEY

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
    memory.py            демо-данные (backend=memory)
    supabase.py          PostgREST-клиент и маппинг таблицы triggers (backend=supabase)
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
| `/prospects` | список брифов из `researched_documents`, поиск по имени и запросу |
| `/prospects/<id>` | досье: `full_markdown` отрендерен в HTML + оглавление |
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

## Supabase

Таблица `triggers` читается через PostgREST (`/rest/v1/triggers`) на stdlib —
дополнительных зависимостей нет. Маппинг колонок в модель — в
`app/repositories/supabase.py`:

| Колонка таблицы | Поле в UI |
|---|---|
| `event_date` | Date |
| `company_or_person` | Event (хвост `(bidder: …)` отрезается) |
| `context` | Headline = первое предложение; полный текст в раскрытой строке |
| `trigger_type` | тип события и значения фильтра Category |
| `bidder` / `seller` | Counterparties, Principal |
| `source` | ссылка + домен как имя источника |
| `created_at`, `founded` | «Ingested … · reviewed by …» |

Колонок под Est. size, Confidence и Individuals in scope в таблице нет —
в этих местах UI показывает «—». Как только колонки появятся, достаточно
заполнить соответствующие поля в `row_to_trigger()`.

Если Supabase недоступен или ключ неверный, страница не падает: показывается
предупреждение, остальной интерфейс продолжает работать.

## Prospect Brief

Список и досье читаются из таблицы `researched_documents`:

| Колонка | Где видно |
|---|---|
| `name` | заголовок строки и досье |
| `source_query` | подпись «Research query» |
| `document_type`, `status` | колонки Type и Status (значок completed / running) |
| `researched_at` | колонка Researched |
| `full_markdown` | тело досье |

Поиск идёт по `name`, `normalized_name` и `source_query` (PostgREST `ilike`).
В списке `full_markdown` не запрашивается — колонка весит десятки килобайт
на строку и в перечне не нужна.

Досье рендерится целиком из markdown (`app/services/markdown_render.py`):
заголовки, списки и таблицы получают стиль макета, слева собирается
оглавление по разделам. Текст пишет LLM по материалам из открытых
источников, поэтому HTML после конвертации проходит через белый список
тегов — скрипты и обработчики событий вырезаются, внешние ссылки получают
`rel="noopener noreferrer"`.

Если у записи пустой `full_markdown` (исследование ещё идёт), досье
открывается и объясняет, почему содержимого нет.

### Download PDF

`GET /prospects/<id>/pdf` собирает PDF из того же санированного HTML, что
показывается на странице, — экран и файл не расходятся. Сборка в
`app/services/pdf_export.py` на reportlab: заголовки, абзацы, списки и
таблицы с повторяющейся шапкой при переносе на следующую страницу,
колонтитул с именем и номером страницы.

reportlab выбран вместо HTML→PDF конвертеров потому, что WeasyPrint требует
системных библиотек (pango, cairo), которых может не быть на хостинге, а
reportlab — чистый Python.

Шрифт DejaVu Sans лежит в `app/static/fonts` (~1.5 МБ на две начертания).
Встроенная в reportlab Helvetica знает только latin-1 и ломается на
кириллице; наличие системных шрифтов на сервере не гарантировано, поэтому
шрифт в репозитории. Если файлов нет, экспорт не падает — откатывается на
Helvetica.

## Кнопка Find triggers

Порт логики из Streamlit-версии (`render_find_trigger_info_section`). Триггеры
не собираются постоянно — только по нажатию кнопки на странице `/triggers`:

1. `app/scraping/scraper.py` обходит источники выбранной категории
   (RSS, при его отсутствии — ссылки с главной), фильтрует заголовки по
   ключевым словам, забирает текст статей и отсекает всё старше look-back.
2. Собранные статьи уходят POST-ом в n8n (`N8N_TRIGGERS_SCAN_WEBHOOK_URL`)
   вместе с `job_id` — контракт тот же, что был в Streamlit:
   `{action: "scan_trigger", category, job_id, articles: [...]}`.
3. Приложение опрашивает таблицу `trigger_jobs` по `job_id`, пока n8n не
   поставит `status = done` (с `inserted_count`) или `error`.
4. На странице появляется «Found N article(s) · Added M new trigger(s)»,
   список триггеров перечитывается из базы.

Отличие от Streamlit только в исполнении: там кнопка блокировала поток на
несколько минут, здесь сканирование уходит в фоновый поток, а страница
опрашивает `GET /api/v1/scan/<job_id>` раз в 2 секунды и показывает живой лог.
HTTP-запрос при этом не висит и не упирается в таймаут gunicorn.

Источники и «уже известные» ссылки настраиваются в
`app/scraping/domains_by_category.json` — код для этого править не нужно.

Задачи сканирования хранятся в памяти процесса, поэтому воркер должен быть
один (`gunicorn -w 1`); при рестарте незавершённая задача теряется.

### Что дальше

Прочие экраны (Prospect Brief, досье, watchlist) ждут своих таблиц.
Порядок подключения тот же: класс в `app/repositories/`, реализующий протокол
из `base.py`, и ветка в `app/repositories/__init__.py`. Шаблоны, сервисы и API
менять не нужно.
