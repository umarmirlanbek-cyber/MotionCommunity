from drf_yasg.inspectors import SwaggerAutoSchema

TAG_NAMES = {
    'auth': 'Вход',
    'me': 'Личный кабинет',
    'members': 'Участники',
    'users': 'Пользователи (админка)',
    'teams': 'Команды',
    'projects': 'Проекты',
    'client-requests': 'Заявки клиентов',
    'choices': 'Общее',
    'stats': 'Общее',
}

# (кого добавить/получить, чего список)
NOUNS = {
    'members': ('участника', 'участников'),
    'users': ('пользователя', 'пользователей'),
    'teams': ('команду', 'команд'),
    'projects': ('проект', 'проектов'),
    'client-requests': ('заявку', 'заявок'),
    'work': ('место работы', 'мест работы'),
    'education': ('образование', 'образований'),
    'languages': ('язык', 'языков'),
    'certificates': ('сертификат', 'сертификатов'),
}

SPECIAL = {
    'login': 'Войти',
    'logout': 'Выйти',
    'refresh': 'Обновить токен',
    'verify': 'Проверить токен',
    'choices': 'Значения для списков',
    'stats': 'Статистика',
    'password': 'Сменить пароль',
}

ME_ACTIONS = {
    'read': 'Мой профиль',
    'partial_update': 'Изменить профиль',
    'delete': 'Удалить аккаунт',
}


class SectionAutoSchema(SwaggerAutoSchema):
    def get_tags(self, operation_keys=None):
        operation_keys = operation_keys or self.operation_keys
        section = operation_keys[1] if len(operation_keys) > 1 else operation_keys[0]
        return [TAG_NAMES.get(section, section)]

    def get_summary_and_description(self):
        summary, description = super().get_summary_and_description()
        if self.overrides.get('operation_summary'):
            return summary, description

        keys = self.operation_keys
        action, resource = keys[-1], keys[-2]

        if resource in SPECIAL:
            return SPECIAL[resource], description
        if resource == 'me':
            return ME_ACTIONS.get(action, summary), description
        if resource in NOUNS:
            single, plural = NOUNS[resource]
            verbs = {
                'create': f'Добавить {single}',
                'read': f'Получить {single}',
                'partial_update': f'Изменить {single}',
                'delete': f'Удалить {single}',
            }
            if action == 'list':
                return f'Список {plural}', description
            return verbs.get(action, summary), description
        return summary, description