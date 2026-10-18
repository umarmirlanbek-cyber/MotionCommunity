# Motion Community — бэкенд

Сайт сообщества Motion: участники и их резюме, команды, проекты и заявки от клиентов.
Django 6.1 + Django REST Framework + JWT.

Фронту читать **[API.md](API.md)** — там все адреса и правила.

## Где что лежит

Всё API живёт в одном приложении `motion_app`.

```
my_site/
├── my_site/      настройки (settings.py) и корневые адреса (urls.py): админка, Swagger, /api/<язык>/
├── motion_app/   приложение
└── nginx/        конфиг nginx для докера
```

Внутри `motion_app`:

| Файл | Что в нём |
| --- | --- |
| `models.py` | таблицы в базе |
| `choices.py` | все варианты выбора: роли, должности, статусы |
| `serializers.py` | какие поля уходят во фронт и приходят от него |
| `views.py` | что делает каждый адрес |
| `permission.py` | кто что может |
| `urls.py` | все адреса API |
| `admin.py` | как это выглядит в Django-админке |
| `translations.py` | какие поля переводятся на английский |
| `middleware.py` | включает язык из адреса `/api/ru/...` |
| `tests.py` | тесты |

В больших файлах разделы отбиты строками `# ---------- Команды ----------`.

## Как идёт запрос

`GET /api/ru/projects/1/`:

1. `motion_app/middleware.py` видит `ru` в адресе и включает русский язык.
2. `motion_app/urls.py` находит адрес `projects/1/`.
3. `motion_app/views.py` (`ProjectViewSet`) проверяет права и берёт проект из базы.
4. `motion_app/serializers.py` (`ProjectDetailSerializer`) превращает его в JSON.

## Обновление существующей базы

Миграции продолжают миграции master (`0001`–`0004`). Перед обновлением сделайте копию базы, потом выполните `python manage.py migrate`:

- поля переименуются, данные и id пользователей останутся;
- суперпользователи получат роль `Admin`, все остальные — `Member`;
- роль `Developer` в командах и проектах станет `Member`;
- годы учёбы превратятся в числа.

## Запуск на своём компьютере

```bash
cd my_site
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r req.txt
cp .env.example .env              # и впишите SECRET_KEY
python manage.py migrate
python manage.py seed_data        # тестовые данные: admin / Admin12345!
python manage.py runserver
```

Swagger: http://127.0.0.1:8000/api/docs/, админка: http://127.0.0.1:8000/admin/.
Локально база — SQLite, ничего настраивать не нужно.

## Тесты

```bash
cd my_site
python manage.py test
```

## Запуск в докере (сервер)

```bash
cd my_site
cp .env.example .env              # DEBUG=False, свои ALLOWED_HOSTS, пароли
docker compose up -d --build
```

Поднимутся три контейнера:

- `db` — Postgres;
- `web` — Django + gunicorn, сам выполнит `migrate`;
- `nginx` — порт 80, раздаёт статику и медиа, проксирует чат на `CHAT_UPSTREAM`.

Создать админа: `docker compose exec web python manage.py createsuperuser`.
Суперпользователь автоматически получает роль `Admin`.

`seed_data` на сервере не запустится: он стирает базу и работает только при `DEBUG=True`.
