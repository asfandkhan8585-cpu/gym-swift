release: python manage.py migrate --noinput
web: gunicorn gymkhana.wsgi:application --bind 0.0.0.0:$PORT --workers 3
