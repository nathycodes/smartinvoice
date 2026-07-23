#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input

python manage.py migrate

python manage.py shell -c "
from django.contrib.auth.models import User
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@smartinvoice.ng', 'admin12345')
    print('Created admin superuser')
if not User.objects.filter(username='ngozi').exists():
    exec(open('seed_demo.py').read())
    print('Seeded demo business')
else:
    print('Demo data already present, skipping seed')
"
