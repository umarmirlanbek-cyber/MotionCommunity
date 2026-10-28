# API Motion Community - памятка для фронта

Живая документация с кнопкой «попробовать»: **`/api/docs/`** (Swagger).
Нажмите **Authorize** и вставьте `Bearer <access-токен>`.

## 8 правил

1. **Адрес = `/api/{язык}/...`**, язык - `ru` или `en`. Пример: `/api/ru/projects/`, `/api/en/projects/`.
   Редиректов нет. От языка зависят только переводимые поля: `bio`, `description` у команд и проектов.
   Если английского текста нет, придёт русский.
2. **Вход:** `POST /api/ru/auth/login/` → `access` и `refresh`.
   Дальше в каждом запросе заголовок `Authorization: Bearer <access>`.
   `access` живёт 30 минут, `refresh` - 7 дней. Новый `access`: `POST /api/ru/auth/refresh/` с `{"refresh": "..."}`.
3. **Любой список приходит страницами:**
   `{"count": 42, "next": "...?page=2", "previous": null, "results": [...]}`.
   На странице 20 записей, следующая - `?page=2`.
4. **Ошибки всегда одной формы:**
   - `400` - `{"имя_поля": ["что не так"]}`
   - `401`, `403`, `404` - `{"detail": "что не так"}`. Несуществующий адрес под `/api/` тоже отвечает JSON: `{"detail": "Страница не найдена."}` (локально с `DEBUG=True` Django показывает свою HTML-страницу)
   - `429` - слишком много запросов, подождите. Без входа можно 120 запросов в минуту, с входом - 600
5. **Связи:** отправляете `что-то_id`, получаете `что-то` объектом.
   Отправили `{"user_id": 5}` - получили `{"user": {"id": 5, "first_name": "...", ...}}`.
6. **Значения для выпадающих списков** (должности, статусы, роли) не хардкодим: `GET /api/ru/choices/`.
7. **Файлы** (аватар, резюме, картинки) отправляются через `multipart/form-data`.
   Резюме - только `pdf`, `doc`, `docx`. Любой файл - до 5 МБ.
8. **Роли простые:**
   - `Admin` - может всё;
   - `Member` - обычный участник;
   - `Team_Lead` - роль только внутри конкретной команды или проекта.

## Все адреса

Ниже пути после `/api/{язык}/`. «Все» - без входа. «Вошедший» - с токеном.

### Вход

| Метод | Путь | Кто | Что отправить → что придёт |
| --- | --- | --- | --- |
| POST | `auth/login/` | все | `{username, password}` → `{access, refresh, user: {id, username, role, status}}`. Не больше 10 попыток в минуту |
| POST | `auth/refresh/` | все | `{refresh}` → `{access}` |
| POST | `auth/logout/` | все | `{refresh}` → `205`. Токен access не нужен, выйти можно и с истёкшим. Неверный или уже отозванный refresh → `400` |
| GET | `auth/verify/` | вошедший | `{id, username, role}` - для сервиса чата |

### Личный кабинет

Всё о себе, вместе с резюме, приходит одним запросом `GET me/`. Остальные адреса только добавляют, меняют и удаляют.

| Метод | Путь | Кто | Что |
| --- | --- | --- | --- |
| GET | `me/` | вошедший | Профиль целиком: поля профиля, `work`, `education`, `languages`, `certificates`, `teams`, `projects`, `username`, `email`, `role`, `status` |
| PATCH | `me/` | вошедший | Любые поля профиля, кроме `username`, `role` и `status`. Профиль становится `Active`, когда заполнено имя, «о себе» или навыки |
| DELETE | `me/` | вошедший | Удалить свой аккаунт. Человек пропадёт из команд и проектов |
| POST | `me/password/` | вошедший | `{old_password, new_password}`. Все токены, и refresh, и текущий access, сразу перестают работать (`401`): после смены пароля войдите заново |
| POST | `me/work/` | вошедший | Добавить опыт работы: `{company, position, start_date, end_date, working_format, achievements}` → запись с `id` |
| PATCH, DELETE | `me/work/{id}/` | вошедший | Изменить или удалить запись (только свою) |
| POST | `me/education/` | вошедший | `{institution, specialization, start_year, end_year, studying_now, description}`, годы - числа (`2021`) |
| POST | `me/languages/` | вошедший | `{name, level}` |
| POST | `me/certificates/` | вошедший | `{title, organization, issue_date, description, image}` |

Для `education`, `languages` и `certificates` адрес `.../{id}/` работает так же, как у `work`: `PATCH` и `DELETE`.

### Участники (публичная витрина)

| Метод | Путь | Кто | Что |
| --- | --- | --- | --- |
| GET | `members/` | все | Только заполненные профили. Фильтры `?position=`, `?search=` (имя, фамилия, навыки) |
| GET | `members/{id}/` | все | Публичный профиль с резюме, командами и проектами |

### Пользователи (админка на фронте)

| Метод | Путь | Кто | Что |
| --- | --- | --- | --- |
| GET | `users/` | Admin | Фильтры `?role=`, `?status=`, `?is_active=`, `?search=` |
| POST | `users/` | Admin | `{username, password, role}` - выдать логин новому участнику |
| GET, PATCH, DELETE | `users/{id}/` | Admin | `is_active: false` - заблокировать без удаления. Новый `password` или блокировка отзывают все токены пользователя. Последнего Admin нельзя удалить, понизить или заблокировать → `400` (так же для `DELETE me/`) |

### Команды

| Метод | Путь | Кто | Что |
| --- | --- | --- | --- |
| GET | `teams/` | вошедший | `{id, name, image, members_count}`, `?search=` |
| POST | `teams/` | Admin | `{name, description, image}` |
| GET | `teams/{id}/` | вошедший | Команда + `members` + `projects` |
| PATCH, DELETE | `teams/{id}/` | Admin | При удалении проекты остаются, просто без команды |
| GET | `teams/{team_id}/members/` | вошедший | Состав |
| POST | `teams/{team_id}/members/` | Admin или тимлид этой команды | `{user_id, role}`. Назначить `Team_Lead` может только Admin. Заблокированного пользователя добавить нельзя → `400` |
| PATCH | `teams/{team_id}/members/{user_id}/` | Admin | `{role}` |
| DELETE | `teams/{team_id}/members/{user_id}/` | Admin или тимлид | Тимлид не может убрать другого тимлида |

### Проекты

| Метод | Путь | Кто | Что |
| --- | --- | --- | --- |
| GET | `projects/` | все | Фильтры `?status=`, `?category=`, `?team=`, `?search=`, `?ordering=name` или `-created_at` |
| POST | `projects/` | Admin | `{name, description, category, status, team_id, image, demo_url, github_url}` |
| GET | `projects/{id}/` | все | Проект + `team` + `members` |
| PATCH | `projects/{id}/` | Admin или тимлид проекта | Любые поля. `team_id` меняет только Admin: если тимлид пришлёт другую команду, получит `403`, текущую можно присылать в форме как есть |
| DELETE | `projects/{id}/` | Admin | |
| GET | `projects/{project_id}/members/` | все | Состав |
| POST, PATCH, DELETE | `projects/{project_id}/members/...` | как у команд | Правила те же, что у команд |

### Задачи

Доска задач проекта, как в Jira. Видят задачи и создают их только участники проекта и Admin.

| Метод | Путь | Кто | Что |
| --- | --- | --- | --- |
| GET | `projects/{project_id}/tasks/` | участник проекта | `{id, title, status, priority, type, labels, assignee, due_date, order}`. Фильтры `?status=`, `?priority=`, `?type=`, `?label=`, `?assignee=`, `?search=` (название) |
| POST | `projects/{project_id}/tasks/` | участник проекта | `{title, description, status, priority, type, labels, assignee_id, due_date, order}`, обязательно только `title`. Автором становится тот, кто создал |
| GET | `projects/{project_id}/tasks/labels/` | участник проекта | Все метки задач проекта: `["backend", "frontend"]` |
| GET | `projects/{project_id}/tasks/{id}/` | участник проекта | Задача + `author` + `comments` + `attachments` + `history` |
| PATCH | `projects/{project_id}/tasks/{id}/` | Admin, тимлид проекта, исполнитель или автор задачи | Любые поля. Карточку перетащили - `{status, order}` |
| DELETE | `projects/{project_id}/tasks/{id}/` | Admin или тимлид проекта | |
| POST | `projects/{project_id}/tasks/{task_id}/comments/` | участник проекта | `{text}` |
| PATCH | `projects/{project_id}/tasks/{task_id}/comments/{id}/` | автор комментария | `{text}` |
| DELETE | `projects/{project_id}/tasks/{task_id}/comments/{id}/` | автор, Admin или тимлид проекта | |
| POST | `projects/{project_id}/tasks/{task_id}/attachments/` | участник проекта | `multipart/form-data`, поле `file`, до 10 файлов за раз → список вложений |
| DELETE | `projects/{project_id}/tasks/{task_id}/attachments/{id}/` | автор файла, Admin или тимлид проекта | |
| GET | `me/tasks/` | вошедший | Мои задачи во всех моих проектах (где я исполнитель): поля как в списке + `project: {id, name}`. Фильтры `?status=`, `?priority=`, `?type=`, `?label=` |

#### Колонки, приоритеты и типы

Берутся из `GET choices/`:

- `task_statuses`: `To_do`, `In_progress`, `Review`, `Done`
- `task_priorities`: `Low`, `Medium`, `High`, `Critical`
- `task_types`: `Task`, `Bug`, `Feature`, `Improvement`

Каждый элемент - `{value, label}`, в `label` подпись по-русски.

#### Доска проекта

`GET projects/{project_id}/tasks/`. Видят участники проекта и Admin, остальным `403`.

Фильтры: `?status=To_do`, `?priority=High`, `?type=Bug`, `?label=backend`, `?assignee=4` (id пользователя), `?search=` (по названию).
Ответ приходит страницами по 20, следующая страница - `?page=2`. Поэтому доску удобнее грузить четырьмя запросами, по одному на колонку: `?status=To_do`, `?status=In_progress` и т. д.
Внутри колонки задачи отсортированы по `order`, при равном `order` - по `id`.

```json
{
  "count": 2, "next": null, "previous": null,
  "results": [
    {
      "id": 1,
      "title": "Сверстать страницу курса",
      "status": "To_do",
      "priority": "Medium",
      "type": "Feature",
      "labels": ["frontend"],
      "assignee": {"id": 2, "first_name": "Нурлан", "last_name": "Асанов", "position": "Fullstack_Developer", "avatar": null},
      "due_date": null,
      "order": 0
    }
  ]
}
```

`assignee` бывает `null`, если задача ни на кого не назначена.

#### Создать задачу

`POST projects/{project_id}/tasks/`. Может любой участник проекта.

```json
{
  "title": "Форма регистрации",
  "description": "Поля: имя, почта, пароль",
  "status": "To_do",
  "priority": "High",
  "type": "Feature",
  "labels": ["frontend", "auth"],
  "assignee_id": 4,
  "due_date": "2026-11-01",
  "order": 0
}
```

Обязательно только `title`. По умолчанию `status: To_do`, `priority: Medium`, `type: Task`, `labels: []`, `order: 0`.
`assignee_id` - только активный (не заблокированный) участник этого проекта, иначе `400`. Список участников отдаёт `GET projects/{id}/members/`.
Автор ставится сам, это тот, кто создал задачу. В ответ приходит `201` и задача целиком, как в карточке.

#### Карточка задачи

`GET projects/{project_id}/tasks/{id}/`

```json
{
  "id": 6,
  "title": "Форма регистрации",
  "description": "Поля: имя, почта, пароль",
  "status": "In_progress",
  "priority": "High",
  "type": "Feature",
  "labels": ["frontend", "auth"],
  "assignee": {"id": 4, "first_name": "Азамат", "last_name": "Кубанычбеков", "position": "Frontend_Developer", "avatar": null},
  "author": {"id": 4, "first_name": "Азамат", "last_name": "Кубанычбеков", "position": "Frontend_Developer", "avatar": null},
  "due_date": "2026-11-01",
  "order": 1,
  "created_at": "2026-10-22T13:42:40+06:00",
  "updated_at": "2026-10-22T13:42:40+06:00",
  "comments": [
    {
      "id": 2,
      "author": {"id": 4, "first_name": "Азамат", "last_name": "Кубанычбеков", "position": "Frontend_Developer", "avatar": null},
      "text": "Начал, сегодня закончу",
      "created_at": "2026-10-22T13:42:40+06:00"
    }
  ],
  "attachments": [
    {
      "id": 1,
      "author": {"id": 4, "first_name": "Азамат", "last_name": "Кубанычбеков", "position": "Frontend_Developer", "avatar": null},
      "file": "https://<домен>/api/ru/task-files/<подпись>/",
      "name": "screen.png",
      "created_at": "2026-10-22T14:01:02+06:00"
    }
  ],
  "history": [
    {
      "id": 3,
      "user": {"id": 4, "first_name": "Азамат", "last_name": "Кубанычбеков", "position": "Frontend_Developer", "avatar": null},
      "field": "status",
      "old_value": "To_do",
      "new_value": "In_progress",
      "created_at": "2026-10-22T14:05:11+06:00"
    }
  ]
}
```

У `assignee` и `author` те же поля, что у участника: `id, first_name, last_name, position, avatar`. `author` бывает `null`, если его аккаунт удалили.

#### Изменить или перетащить

`PATCH projects/{project_id}/tasks/{id}/`. Отправляем только то, что поменялось:

- перетащили карточку: `{"status": "In_progress", "order": 1}`
- переназначили: `{"assignee_id": 7}`, сняли исполнителя: `{"assignee_id": null}`
- поправили текст: `{"title": "...", "description": "..."}`

Менять задачу могут Admin, тимлид проекта, исполнитель или автор задачи. Остальные получат `403` `{"detail": "Менять можно только свои задачи"}`, тогда карточку надо вернуть на место.
Соседние карточки бэкенд сам не перенумеровывает. Совет: при создании ставьте `order` с шагом 1000 (1000, 2000, 3000). Тогда для вставки между двумя карточками хватит одного `PATCH` с числом посередине.
В ответ приходит `200` и задача целиком.

#### История изменений

Приходит в карточке задачи, в поле `history`, старые записи сверху. Одна запись - одно поле, которое поменяли через `PATCH`:

- `field`: `title`, `status`, `priority`, `type`, `labels`, `assignee` или `due_date`.
- `old_value`, `new_value` - всегда строки:
  - для `status`, `priority` и `type` приходит значение (`In_progress`), подпись берите из `choices/`;
  - для `assignee` - имя и логин: `Азамат Кубанычбеков (@dev1)`, а если имя не заполнено - только логин;
  - для `labels` - метки через запятую;
  - пустая строка - значения не было (без исполнителя, без срока).
- `user` - кто поменял.

Порядок внутри колонки (`order`) и описание в историю не попадают.

#### Тип и метки

- `type` - один из `task_types`. По умолчанию `Task`.
- `labels` - список строк, например `["backend", "auth"]`. До 10 меток, каждая до 50 символов и без запятых, повторы убираются сами.
  Задачу с метками отправляйте JSON-телом, не формой.
- Метки свободные: новая появляется, когда её впервые поставили в задачу.
  `PATCH` с `labels` заменяет список целиком, `{"labels": []}` снимает все.
- Подсказки при вводе: `GET projects/{project_id}/tasks/labels/` → `["auth", "backend", "frontend"]`, все метки проекта по алфавиту.
- На доске: `?type=Bug`, `?label=backend` (задачи, где есть эта метка).

#### Удалить

`DELETE projects/{project_id}/tasks/{id}/` → `204` без тела. Удалять могут только Admin и тимлид проекта.
Роль пользователя в проекте есть в `GET me/` → `projects[].role` (`Team_Lead` или `Member`), по ней можно прятать кнопки.

#### Комментарии

- добавить: `POST projects/{project_id}/tasks/{task_id}/comments/` с `{"text": "..."}` → `201` `{id, author, text, created_at}`. Может любой участник проекта.
- изменить: `PATCH .../comments/{id}/` с `{"text": "..."}` → `200`. Только автор комментария.
- удалить: `DELETE .../comments/{id}/` → `204`. Автор, тимлид или Admin.

Отдельного адреса для списка комментариев нет: они приходят в карточке задачи, старые сверху.

#### Вложения

- загрузить: `POST projects/{project_id}/tasks/{task_id}/attachments/`, `multipart/form-data`, поле `file`. Может любой участник проекта.
  В одном запросе можно отправить до 10 файлов: поле `file` повторяется для каждого (в `FormData` - `append('file', ...)` на каждый файл).
  Ответ `201` - всегда список `[{id, author, file, name, created_at}]` в том же порядке, даже если файл один.
  Если хоть один файл не подходит, не сохраняется ничего: `400` `{"file": ["page.html: ..."]}`, в начале каждой ошибки имя файла. Больше 10 файлов → `400`.
- форматы: `png`, `jpg`, `jpeg`, `gif`, `webp`, `pdf`, `doc`, `docx`, `xls`, `xlsx`, `txt`, `zip`, до 5 МБ. Остальное → `400`.
- удалить: `DELETE .../attachments/{id}/` → `204`. Автор файла, тимлид или Admin. Файл удаляется и с диска.
- фото при создании задачи: сначала `POST projects/{project_id}/tasks/` (JSON, как обычно), потом одним запросом все фото на `.../tasks/{id}/attachments/`. Если фото не загрузились, задача уже создана, загрузку можно повторить.

Список приходит в карточке задачи, в поле `attachments`. `name` - имя файла, как его загрузили.

`file` - подписанная ссылка, она работает без токена, но только час. Файлы задач закрыты, по постоянной ссылке их не скачать.
Устаревшая ссылка отвечает `403`, тогда перезапросите карточку задачи, и придут новые ссылки.
Картинки можно показывать через `<img src>`. Если открыть ссылку напрямую, браузер файл скачает, а не откроет.

#### Мои задачи

`GET me/tasks/` - задачи, где я исполнитель, во всех проектах. Фильтры `?status=`, `?priority=`.
Поля как на доске плюс `"project": {"id": 1, "name": "Motion LMS Platform"}`.

#### Ошибки

- `400`: `{"поле": ["что не так"]}`, например `{"title": ["Обязательное поле."]}` или `{"assignee_id": ["Исполнитель должен быть активным участником проекта"]}`
- `401`: токена нет или он истёк. Обновить токен можно через `auth/refresh/`.
- `403`: `{"detail": "..."}`, пользователь не участник проекта или ему не хватает прав.
- `404`: задачи нет или она из другого проекта.

### Уведомления

| Метод | Путь | Кто | Что |
| --- | --- | --- | --- |
| GET | `me/notifications/` | вошедший | Мои уведомления, новые сверху. Фильтры `?is_read=false`, `?type=` |
| PATCH | `me/notifications/{id}/` | вошедший | `{"is_read": true}` - отметить прочитанным |
| POST | `me/notifications/read-all/` | вошедший | Отметить все прочитанными → `{"updated": 3}` |

Когда приходят (`type`, подписи в `choices/` → `notification_types`):

- `Assigned` - меня назначили исполнителем: при создании задачи или при смене `assignee_id`.
- `Comment` - новый комментарий в задаче, где я исполнитель или автор.
- `Mention` - меня упомянули в комментарии через `@логин`. Срабатывает только для участников проекта.
  `@` должна стоять в начале текста или после пробела, скобки, запятой: адрес почты `support@team.dev` упоминанием не считается.
  Логин берётся целиком, вместе с точками и `@` внутри (`@anna@corp` - это пользователь `anna@corp`). Точка в конце предложения отбрасывается: `@dev2.` упомянет `dev2`.
  В одном комментарии учитываются первые 50 упоминаний.
  Если меня упомянули, `Comment` на тот же комментарий уже не придёт.

Себе уведомления не приходят: сам назначил себя или сам написал комментарий - ничего не будет.
Уведомления приходят только участникам проекта. Кого убрали из проекта, того снимают с его задач в этом проекте (это видно в истории), а его уведомления по этому проекту удаляются, и новые не приходят.

```json
{
  "id": 1,
  "type": "Mention",
  "actor": {"id": 4, "first_name": "Азамат", "last_name": "Кубанычбеков", "position": "Frontend_Developer", "avatar": null},
  "task": {"id": 4, "title": "Вход через Google", "project": {"id": 1, "name": "Motion LMS Platform"}},
  "comment": {"id": 2, "text": "@dev6 глянь вёрстку"},
  "is_read": false,
  "created_at": "2026-10-23T20:41:24.586885+06:00"
}
```

- `actor` - кто сделал действие, `null`, если его аккаунт удалили. У `Assigned` поле `comment` равно `null`.
- По `task.project.id` и `task.id` можно открыть карточку задачи.
- Счётчик на колокольчике - `count` из `GET me/notifications/?is_read=false`.
- Сами уведомления на фронт не прилетают, WebSocket тут нет. Фронт опрашивает этот адрес, например раз в минуту.

### Заявки клиентов

| Метод | Путь | Кто | Что |
| --- | --- | --- | --- |
| POST | `client-requests/` | все | `{name, company, email, phone, title, description, project_type, budget}`. Не больше 10 в час с одного адреса |
| GET | `client-requests/` | Admin | `?status=`, `?search=` |
| GET, PATCH | `client-requests/{id}/` | Admin | Поменять `status`: `New` → `Reviewing` → `Accepted` или `Rejected`. В ответе `project: {id, name}` или `null`. Заявку, по которой создан проект, отклонить нельзя → `400` |
| POST | `client-requests/{id}/project/` | Admin | Создать проект из заявки, тело не нужно. Название берётся из `title`, описание из `description`, категория из `project_type`. Заявка станет `Accepted`. Ответ `201` - проект, как в `GET projects/{id}/`. Второй раз или по заявке `Rejected` → `400` |

Команду, участников и картинку созданному проекту ставят обычным `PATCH projects/{id}/`.

### Общее

| Метод | Путь | Кто | Что |
| --- | --- | --- | --- |
| GET | `stats/` | все | `{members_count, teams_count, projects_count, companies_count}`. Компании - только по принятым заявкам. Цифры обновляются раз в минуту |
| GET | `choices/` | все | Все варианты выбора: `[{value, label}]` |
| GET | `health/` | все | `{"status": "ok"}` или `503`, если база недоступна. Для проверки сервера |

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
| `/ru/...` (без префикса - редирект 302) | `/api/ru/...`, редиректов нет |
| `user.login` в ответе входа и в админских списках | `username` |
| `/ru/auth/login/refresh/` | `/api/ru/auth/refresh/` |
| `/ru/admin/members/` (не работал) | `/api/ru/users/` |
| `PATCH /ru/members/{id}/` | `PATCH /api/ru/me/` |
| `/ru/personal-account/` | `/api/ru/me/` |
| `work_user`, `education_user`, `language_user`, `certificate_user` | `work`, `education`, `languages`, `certificates` |
| пароль в `PATCH personal-account` | `POST /api/ru/me/password/` со старым паролем |
| `/ru/personal-account/work/` · `start_time`, `end_time` | `/api/ru/me/work/` · `start_date`, `end_date` |
| `GET` опыта, образования, языков и сертификатов по отдельности | всё резюме приходит в `GET /api/ru/me/` |
| `PUT` в разделах резюме | `PATCH` |
| `educational_institution`, `responsibilities`, годы датой | `institution`, `description`, годы числом |
| `Level`, `languages`, уровень `Родной язык` | `level`, `name`, уровень `Native` |
| `given_date`, `text`, `certificate_image` | `issue_date`, `description`, `image` |
| `team_name`, `team_image` | `name`, `image` |
| `project_status`, `preview_image`, `?project_status=` | `status`, `image`, `?status=` |
| в составе команды `user: 5` | `user: {id, first_name, last_name, position, avatar}`, отправлять `user_id` |
| у проекта `team: 1` | `team: {id, name, image}`, отправлять `team_id` |
| глобальные роли `Team_Lead`, `Developer` | `Member` (тимлид - только внутри команды/проекта) |
| роль в команде `Developer` | `Member` |
| должность `UI/UX_Designer` | `UI_UX_Designer` |
| статусы заявки `New`, `Reviewing` | плюс `Accepted`, `Rejected` |
| `/ru/docs/`, `/ru/docs.json` | `/api/docs/`, `/api/docs.json` |
