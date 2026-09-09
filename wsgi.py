"""Точка входа для WSGI-серверов (gunicorn/uwsgi) и `flask run`.

    flask --app wsgi run --debug
    gunicorn -w 4 -b 0.0.0.0:8000 wsgi:app
"""

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
