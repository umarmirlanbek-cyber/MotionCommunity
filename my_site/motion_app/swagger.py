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


class SectionAutoSchema(SwaggerAutoSchema):
    def get_tags(self, operation_keys=None):
        operation_keys = operation_keys or self.operation_keys
        section = operation_keys[1] if len(operation_keys) > 1 else operation_keys[0]
        return [TAG_NAMES.get(section, section)]