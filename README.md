# Motion Community — бэкенд

Сайт сообщества Motion: участники и их резюме, команды, проекты с доской задач и заявки от клиентов.
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

Если на сервере уже работает версия из master с `db.sqlite3` — сначала [переезд на Postgres](#переезд-сервера-с-sqlite-на-postgres).

```bash
cd my_site
cp .env.example .env              # DEBUG=False, свои ALLOWED_HOSTS, пароли
docker compose up -d --build
```

Поднимутся три контейнера:

- `db` — Postgres;
- `web` — Django + gunicorn, сам выполнит `migrate`;
- `nginx` — порт 80, раздаёт статику и медиа, проксирует чат на `CHAT_UPSTREAM`.

Чат — отдельный сервис в той же сети `motion_network`. Он проверяет токены запросом в `http://web:8000/api/ru/auth/verify/`, поэтому в `ALLOWED_HOSTS` должен быть `web`.

Создать админа: `docker compose exec web python manage.py createsuperuser`.
Суперпользователь автоматически получает роль `Admin`.

`seed_data` на сервере не запустится: он стирает базу и работает только при `DEBUG=True`.

## Переезд сервера с SQLite на Postgres

В master база — файл `db.sqlite3` в папке репозитория. Здесь в докере работает Postgres, данные переносятся один раз.
Всё выполняется на сервере в папке `my_site`.

1. Остановить сайт и унести базу из папки. Именно `mv`: пока файл лежит в папке, git не переключит ветку.

   ```bash
   docker compose down
   mv db.sqlite3 ~/motion-backup.sqlite3
   cp ~/motion-backup.sqlite3 ~/motion-move.sqlite3
   ```

   `motion-backup` не трогаем — он для отката. Переносим из `motion-move`.

2. Взять новый код: `git fetch origin && git checkout refactor/clear-structure` (когда ветку вольют — `git pull` в master).

3. Дописать в `.env` по образцу `.env.example`:
   - `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`;
   - новый `SECRET_KEY`: `python3 -c "import secrets; print(secrets.token_urlsafe(50))"`;
   - `DEBUG=False`, в `ALLOWED_HOSTS` — домен сайта и `web`.

4. Поднять сайт с пустым Postgres, `web` сам создаст таблицы:

   ```bash
   docker compose up -d --build
   ```

5. Перенести данные:

   ```bash
   docker compose run --rm -T -e POSTGRES_HOST= -v $HOME/motion-move.sqlite3:/app/db.sqlite3 web python manage.py migrate
   docker compose run --rm -T -e POSTGRES_HOST= -v $HOME/motion-move.sqlite3:/app/db.sqlite3 web python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.permission -e sessions > ~/motion-data.json
   docker compose exec -T web python manage.py loaddata --format=json - < ~/motion-data.json
   ```

   Пустой `POSTGRES_HOST=` значит, что первые две команды работают со старым файлом:
   первая переводит его на новые таблицы, вторая выгружает данные в `motion-data.json`. Третья загружает их в Postgres.

6. Проверить: последняя команда пишет `Installed N object(s)`, где `N` больше нуля.
   В админке на месте пользователи, команды, проекты и заявки.
   Сессии не переносятся, а `SECRET_KEY` новый, поэтому всем придётся войти заново.
   Аватары и резюме лежат в томе `media_volume`, переезд их не трогает.

7. Удалить `~/motion-move.sqlite3` и `~/motion-data.json`: в них хеши паролей и контакты.
   `~/motion-backup.sqlite3` держать, пока не убедитесь, что всё работает.

Если что-то пошло не так — вернуть как было:

```bash
docker compose down
git checkout master
cp ~/motion-backup.sqlite3 db.sqlite3
docker compose up -d --build
```
