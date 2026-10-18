# API Motion Community — памятка для фронта

Живая документация с кнопкой «попробовать»: **`/api/docs/`** (Swagger).
Нажмите **Authorize** и вставьте `Bearer <access-токен>`.

## 8 правил

1. **Адрес = `/api/{язык}/...`**, язык — `ru` или `en`. Пример: `/api/ru/projects/`, `/api/en/projects/`.
   Редиректов нет. От языка зависят только переводимые поля: `bio`, `description` у команд и проектов.
   Если английского текста нет, придёт русский.
2. **Вход:** `POST /api/ru/auth/login/` → `access` и `refresh`.
   Дальше в каждом запросе заголовок `Authorization: Bearer <access>`.
   `access` живёт 30 минут, `refresh` — 7 дней. Новый `access`: `POST /api/ru/auth/refresh/` с `{"refresh": "..."}`.
3. **Любой список приходит страницами:**
   `{"count": 42, "next": "...?page=2", "previous": null, "results": [...]}`.
   На странице 20 записей, следующая — `?page=2`.
4. **Ошибки всегда одной формы:**
   - `400` — `{"имя_поля": ["что не так"]}`
   - `401`, `403`, `404` — `{"detail": "что не так"}`
   - `429` — слишком много запросов, подождите
5. **Связи:** отправляете `что-то_id`, получаете `что-то` объектом.
   Отправили `{"user_id": 5}` — получили `{"user": {"id": 5, "first_name": "...", ...}}`.
6. **Значения для выпадающих списков** (должности, статусы, роли) не хардкодим: `GET /api/ru/choices/`.
7. **Файлы** (аватар, резюме, картинки) отправляются через `multipart/form-data`.
   Резюме — только `pdf`, `doc`, `docx`. Любой файл — до 5 МБ.
8. **Роли простые:**
   - `Admin` — может всё;
   - `Member` — обычный участник;
   - `Team_Lead` — роль только внутри конкретной команды или проекта.

## Все адреса

Ниже пути после `/api/{язык}/`. «Все» — без входа. «Вошедший» — с токеном.

### Вход

| Метод | Путь | Кто | Что отправить → что придёт |
| --- | --- | --- | --- |
| POST | `auth/login/` | все | `{username, password}` → `{access, refresh, user: {id, username, role, status}}`. Не больше 10 попыток в минуту |
| POST | `auth/refresh/` | все | `{refresh}` → `{access}` |
| POST | `auth/logout/` | вошедший | `{refresh}` → `205` |
| GET | `auth/verify/` | вошедший | `{id, username, role}` — для сервиса чата |

### Личный кабинет

| Метод | Путь | Кто | Что |
| --- | --- | --- | --- |
| GET | `me/` | вошедший | Профиль целиком: поля профиля, `work`, `education`, `languages`, `certificates`, `teams`, `projects`, `username`, `email`, `role`, `status` |
| PATCH | `me/` | вошедший | Любые поля профиля, кроме `username`, `role` и `status`. Профиль становится `Active`, когда заполнено имя, «о себе» или навыки |
| DELETE | `me/` | вошедший | Удалить свой аккаунт |
| POST | `me/password/` | вошедший | `{old_password, new_password}` |
| GET, POST | `me/work/` | вошедший | Опыт работы: `{company, position, start_date, end_date, working_format, achievements}` |
| GET, PATCH, DELETE | `me/work/{id}/` | вошедший | Одна запись (только своя) |
| GET, POST | `me/education/` | вошедший | `{institution, specialization, start_year, end_year, studying_now, description}`, годы — числа (`2021`) |
| GET, POST | `me/languages/` | вошедший | `{name, level}` |
| GET, POST | `me/certificates/` | вошедший | `{title, organization, issue_date, description, image}` |

Для `education`, `languages` и `certificates` адрес `.../{id}/` работает так же, как у `work`.

### Участники (публичная витрина)

| Метод | Путь | Кто | Что |
| --- | --- | --- | --- |
| GET | `members/` | все | Только заполненные профили. Фильтры `?position=`, `?search=` (имя, фамилия, навыки) |
| GET | `members/{id}/` | все | Публичный профиль с резюме, командами и проектами |

### Пользователи (админка на фронте)

| Метод | Путь | Кто | Что |
| --- | --- | --- | --- |
| GET | `users/` | Admin | Фильтры `?role=`, `?status=`, `?is_active=`, `?search=` |
| POST | `users/` | Admin | `{username, password, role}` — выдать логин новому участнику |
| GET, PATCH, DELETE | `users/{id}/` | Admin | `is_active: false` — заблокировать без удаления |

### Команды

| Метод | Путь | Кто | Что |
| --- | --- | --- | --- |
| GET | `teams/` | вошедший | `{id, name, image, members_count}`, `?search=` |
| POST | `teams/` | Admin | `{name, description, image}` |
| GET | `teams/{id}/` | вошедший | Команда + `members` + `projects` |
| PATCH, DELETE | `teams/{id}/` | Admin | При удалении проекты остаются, просто без команды |
| GET | `teams/{team_id}/members/` | вошедший | Состав |
| POST | `teams/{team_id}/members/` | Admin или тимлид этой команды | `{user_id, role}`. Назначить `Team_Lead` может только Admin |
| PATCH | `teams/{team_id}/members/{user_id}/` | Admin | `{role}` |
| DELETE | `teams/{team_id}/members/{user_id}/` | Admin или тимлид | Тимлид не может убрать другого тимлида |

### Проекты

| Метод | Путь | Кто | Что |
| --- | --- | --- | --- |
| GET | `projects/` | все | Фильтры `?status=`, `?category=`, `?team=`, `?search=`, `?ordering=name` или `-created_at` |
| POST | `projects/` | Admin | `{name, description, category, status, team_id, image, demo_url, github_url}` |
| GET | `projects/{id}/` | все | Проект + `team` + `members` |
| PATCH | `projects/{id}/` | Admin или тимлид проекта | Любые поля |
| DELETE | `projects/{id}/` | Admin | |
| GET | `projects/{project_id}/members/` | все | Состав |
| POST, PATCH, DELETE | `projects/{project_id}/members/...` | как у команд | Правила те же, что у команд |

### Заявки клиентов

| Метод | Путь | Кто | Что |
| --- | --- | --- | --- |
| POST | `client-requests/` | все | `{name, company, email, phone, title, description, project_type, budget}`. Не больше 10 в час с одного адреса |
| GET | `client-requests/` | Admin | `?status=`, `?search=` |
| GET, PATCH | `client-requests/{id}/` | Admin | Поменять `status`: `New` → `Reviewing` → `Accepted` или `Rejected` |

### Общее

| Метод | Путь | Кто | Что |
| --- | --- | --- | --- |
| GET | `stats/` | все | `{members_count, teams_count, projects_count, companies_count}`. Компании — только по принятым заявкам |
| GET | `choices/` | все | Все варианты выбора: `[{value, label}]` |

## Пример ответа

`GET /api/ru/projects/1/`

```json
{
  "id": 1,
  "name": "Motion LMS Platform",
  "description": "Платформа для онлайн-обучения студентов Motion",
  "status": "Planned",
  "category": "Education",
  "image": null,
  "demo_url": null,
  "github_url": null,
  "created_at": "2026-10-18T16:19:16+06:00",
  "team": {"id": 1, "name": "Alpha Team", "image": null},
  "members": [
    {
      "user": {"id": 2, "first_name": "Нурлан", "last_name": "Асанов", "position": "Fullstack_Developer", "avatar": null},
      "role": "Team_Lead"
    }
  ]
}
```

## Что поменялось по сравнению с master

| Было | Стало |
| --- | --- |
| `/ru/...` (без префикса — редирект 302) | `/api/ru/...`, редиректов нет |
| `user.login` в ответе входа и в админских списках | `username` |
| `/ru/auth/login/refresh/` | `/api/ru/auth/refresh/` |
| `/ru/admin/members/` (не работал) | `/api/ru/users/` |
| `PATCH /ru/members/{id}/` | `PATCH /api/ru/me/` |
| `/ru/personal-account/` | `/api/ru/me/` |
| `work_user`, `education_user`, `language_user`, `certificate_user` | `work`, `education`, `languages`, `certificates` |
| пароль в `PATCH personal-account` | `POST /api/ru/me/password/` со старым паролем |
| `/ru/personal-account/work/` · `start_time`, `end_time` | `/api/ru/me/work/` · `start_date`, `end_date` |
| `educational_institution`, `responsibilities`, годы датой | `institution`, `description`, годы числом |
| `Level`, `languages`, уровень `Родной язык` | `level`, `name`, уровень `Native` |
| `given_date`, `text`, `certificate_image` | `issue_date`, `description`, `image` |
| `team_name`, `team_image` | `name`, `image` |
| `project_status`, `preview_image`, `?project_status=` | `status`, `image`, `?status=` |
| в составе команды `user: 5` | `user: {id, first_name, last_name, position, avatar}`, отправлять `user_id` |
| у проекта `team: 1` | `team: {id, name, image}`, отправлять `team_id` |
| глобальные роли `Team_Lead`, `Developer` | `Member` (тимлид — только внутри команды/проекта) |
| роль в команде `Developer` | `Member` |
| должность `UI/UX_Designer` | `UI_UX_Designer` |
| статусы заявки `New`, `Reviewing` | плюс `Accepted`, `Rejected` |
| `/ru/docs/`, `/ru/docs.json` | `/api/docs/`, `/api/docs.json` |
