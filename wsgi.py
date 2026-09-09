"""Точка входа для WSGI-серверов (gunicorn/uwsgi) и `flask run`.

Локально:
    flask --app wsgi run --debug
Прод (Render и любой другой хостинг задаёт порт через $PORT):
    gunicorn -w 1 -b 0.0.0.0:$PORT wsgi:app
"""

import os

from dotenv import load_dotenv

# Локально читаем .env; на хостинге переменные приходят из окружения,
# существующие значения load_dotenv не перетирает.
load_dotenv()

from app import create_app  # noqa: E402  (импорт после load_dotenv — так конфиг видит .env)

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), debug=True)
