# Motion Community - бэкенд

Сайт сообщества Motion: участники и их резюме, команды, проекты с доской задач и заявки от клиентов.
Django 6.1 + Django REST Framework + JWT.

Фронту читать **[API.md](API.md)** - там все адреса и правила.

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

Миграции продолжают миграции master (`0001`-`0004`). Перед обновлением сделайте копию базы, потом выполните `python manage.py migrate`:

- поля переименуются, данные и id пользователей останутся;
- суперпользователи получат роль `Admin`, все остальные - `Member`;
- роль `Developer` в командах и проектах станет `Member`;
- годы учёбы превратятся в числа.

## Запуск на своём компьютере

База - только Postgres. Свой Postgres: создайте пользователя и базу, как в `.env`. Или поднимите его в докере:

```bash
docker run -d --name motion-db -p 5432:5432 -e POSTGRES_DB=motion -e POSTGRES_USER=motion -e POSTGRES_PASSWORD=motion postgres:16
```

```bash
cd my_site
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r req.txt
cp .env.example .env              # и впишите SECRET_KEY и пароль Postgres
python manage.py migrate
python manage.py seed_data        # тестовые данные: admin / Admin12345!
python manage.py runserver
```

Swagger: http://127.0.0.1:8000/api/docs/, админка: http://127.0.0.1:8000/admin/.

## Тесты

```bash
cd my_site
python manage.py test
```

Тесты тоже идут на Postgres: Django создаёт базу `test_motion` и удаляет её после прогона.
Пользователю базы нужно право `CREATEDB`, у пользователя из докера оно есть.

На GitHub тесты запускаются сами при каждом пуше в master и в каждом PR (`.github/workflows/tests.yml`).
Там же проверяется, что к изменениям моделей не забыли миграции.

## Запуск в докере (сервер)

Если на сервере ещё работает старая версия с `db.sqlite3` - сначала [переезд на Postgres](#переезд-сервера-с-sqlite-на-postgres).

```bash
cd my_site
cp .env.example .env              # DEBUG=False, свои ALLOWED_HOSTS, пароли
docker compose up -d --build
```

Поднимутся три контейнера:

- `db` - Postgres;
- `web` - Django + gunicorn, сам выполнит `migrate`;
- `nginx` - порт 80, раздаёт статику и медиа, проксирует чат на `CHAT_UPSTREAM`.

Чат - отдельный сервис в той же сети `motion_network`. Он проверяет токены запросом в `http://web:8000/api/ru/auth/verify/`, поэтому в `ALLOWED_HOSTS` должен быть `web`.

Сайт открывается по https - поставьте в `.env`:

- `HTTPS=True`: cookie админки будут ходить только по https;
- `CSRF_TRUSTED_ORIGINS=https://<домен>`, иначе Django не пустит в админку;
- `NUM_PROXIES=2`, если сертификат стоит на отдельном прокси перед этим nginx. Иначе лимиты запросов посчитают всех посетителей одним адресом.

Тот прокси должен передавать заголовок `X-Forwarded-Proto: https`, nginx отдаст его в Django как есть.
Перенаправление с http на https и HSTS настраиваются там, где стоит сертификат.

Защита:

- вход в API - не больше 10 попыток в минуту с адреса, вход в админку - не больше 10 в минуту (nginx);
- без входа - не больше 120 запросов в минуту, с входом - 600;
- файлы задач закрыты: они лежат не в `media`, а в отдельном томе `private_media_volume`. Скачать файл можно только по подписанной ссылке из API, она живёт час. Django проверяет подпись, а сам файл отдаёт nginx (`X-Accel-Redirect`, `TASK_FILES_X_ACCEL=True` в compose). Локально без nginx файл отдаёт Django;
- все загруженные файлы хранятся под случайными именами, старый файл удаляется, когда его заменили или удалили запись;
- смена пароля отзывает все refresh-токены пользователя.

Лимиты считаются в памяти каждого процесса gunicorn, их три, так что на деле лимит до трёх раз выше.
Для точного подсчёта нужен общий кэш, например Redis.
Лимит nginx на вход в админку считается по адресу того, кто подключился к nginx: за отдельным прокси он общий на всех.

`docker compose ps` показывает у `web` состояние `healthy`, если Django отвечает и база доступна (адрес `/api/ru/health/`).
Проверка ходит на `web`, поэтому `web` в `ALLOWED_HOSTS` нужен и для неё.
Ошибки 500 с полным трейсбеком: `docker compose logs web`.

Создать админа: `docker compose exec web python manage.py createsuperuser`.
Суперпользователь автоматически получает роль `Admin`.

`seed_data` на сервере не запустится: он стирает базу и работает только при `DEBUG=True`.

### Обновление сервера

1. Сделать копию тома с файлами: миграция `0017` переносит файлы задач из `media` в `private_media`.
   Имя тома видно в `docker volume ls`, обычно `my_site_media_volume`:

   ```bash
   docker run --rm -v my_site_media_volume:/data -v $HOME:/backup alpine tar czf /backup/motion-media.tgz -C /data .
   ```

2. Обновить: `git pull && docker compose up -d --build`. Миграции `web` применит сам.
3. Проверить файлы задач: `docker compose exec web ls private_media/task_files | head` показывает файлы,
   а в `media/task_files` их больше нет.
4. Открыть в API карточку задачи со старым вложением (лучше с кириллицей в имени) и скачать файл по ссылке
   из `attachments[].file`: должен прийти файл с правильным именем.

## Переезд сервера с SQLite на Postgres

В старой версии база - файл `db.sqlite3` в папке репозитория. Новый код работает только с Postgres, данные переносятся один раз.
Всё выполняется на сервере в папке `my_site`.

1. Остановить сайт и унести базу из папки. Именно `mv`: пока файл лежит в папке, `git pull` не пройдёт.

   ```bash
   docker compose down
   mv db.sqlite3 ~/motion-backup.sqlite3
   mkdir ~/motion-move
   cp ~/motion-backup.sqlite3 ~/motion-move/db.sqlite3
   ```

   `motion-backup` не трогаем - он для отката. Переносим из `motion-move`.

2. Взять версию, на которой работает перенос: `git fetch origin && git checkout 0969437`.
   Это последняя версия до миграций, которые работают только в Postgres: свежий код старый файл SQLite перевести не может.
   До свежего кода сайт обновится на шаге 7.

3. Дописать в `.env` по образцу `.env.example`:
   - `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`;
   - новый `SECRET_KEY`: `python3 -c "import secrets; print(secrets.token_urlsafe(50))"`;
   - `DEBUG=False`, в `ALLOWED_HOSTS` - домен сайта и `web`.

4. Поднять сайт с пустым Postgres, `web` сам создаст таблицы:

   ```bash
   docker compose up -d --build
   ```

5. Перенести данные. Новый код SQLite не читает, поэтому на время переноса рядом со старой базой кладём файл настроек для неё:

   ```bash
   cat > ~/motion-move/move_settings.py <<'EOF'
   from my_site.settings import *
   DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': '/move/db.sqlite3'}}
   EOF
   docker compose run --rm -T -v $HOME/motion-move:/move -e PYTHONPATH=/move -e DJANGO_SETTINGS_MODULE=move_settings web python manage.py migrate
   docker compose run --rm -T -v $HOME/motion-move:/move -e PYTHONPATH=/move -e DJANGO_SETTINGS_MODULE=move_settings web python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.permission -e sessions > ~/motion-data.json
   docker compose exec -T web python manage.py loaddata --format=json - < ~/motion-data.json
   ```

   Первые две команды работают со старым файлом через `move_settings`:
   первая переводит его на новые таблицы, вторая выгружает данные в `motion-data.json`. Третья загружает их в Postgres.

6. Проверить: последняя команда пишет `Installed N object(s)`, где `N` больше нуля.
   В админке на месте пользователи, команды, проекты и заявки.
   Сессии не переносятся, а `SECRET_KEY` новый, поэтому всем придётся войти заново.
   Аватары и резюме лежат в томе `media_volume`, переезд их не трогает.
   Файлы задач, если они уже были загружены, миграция `0017` сама перенесёт из `media` в `private_media`.

7. Перейти на свежий код, `web` сам применит остальные миграции:

   ```bash
   git checkout master && git pull
   docker compose up -d --build
   ```

8. Удалить `~/motion-move` и `~/motion-data.json`: в них хеши паролей и контакты.
   `~/motion-backup.sqlite3` держать, пока не убедитесь, что всё работает.

Если что-то пошло не так - вернуть как было:

```bash
docker compose down
git checkout 81acce9
cp ~/motion-backup.sqlite3 db.sqlite3
docker compose up -d --build
```
