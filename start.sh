#!/usr/bin/env bash
if [ "$FLASK_ENV" = "development" ]; then
    # flask provides debug, hot reload
    python main.py
else
    # WSGI - Flask
    # add gunicor/wsgi in front of flask
    # gunicorn default to 8000
    # main.py module : app = Flask(__name__) object
    # connection timeout seconds
    gunicorn --timeout 60 --bind 0.0.0.0:5000 main:app

    # ASGI - FastAPI
    # uvicorn main:app --host 0.0.0.0 --port 80 --timeout-keep-alive 60
fi