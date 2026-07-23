web: gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 2 --timeout 120 --forwarded-allow-ips='*' --preload main:app
