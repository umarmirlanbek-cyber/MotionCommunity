from drf_yasg.inspectors import SwaggerAutoSchema

TAG_NAMES = {
    'auth': 'Auth',
    'me': 'Me',
    'members': 'Members',
    'users': 'Users',
    'teams': 'Teams',
    'projects': 'Projects',
    'tasks': 'Tasks',
    'client-requests': 'Client requests',
    'choices': 'Common',
    'stats': 'Common',
    'health': 'Common',
}

NOUNS = {
    'members': ('member', 'members'),
    'users': ('user', 'users'),
    'teams': ('team', 'teams'),
    'projects': ('project', 'projects'),
    'client-requests': ('client request', 'client requests'),
    'work': ('work experience', 'work experience'),
    'education': ('education', 'education'),
    'languages': ('language', 'languages'),
    'certificates': ('certificate', 'certificates'),
    'teams/members': ('team member', 'team members'),
    'projects/members': ('project member', 'project members'),
    'tasks': ('task', 'tasks'),
    'comments': ('comment', 'comments'),
    'attachments': ('attachment', 'attachments'),
    'labels': ('label', 'labels'),
    'me/tasks': ('my task', 'my tasks'),
    'me/notifications': ('notification', 'notifications'),
}

SPECIAL = {
    'login': 'Login',
    'logout': 'Logout',
    'refresh': 'Refresh token',
    'verify': 'Verify token',
    'choices': 'Choices',
    'stats': 'Stats',
    'password': 'Change password',
    'health': 'Health check',
    'read-all': 'Mark all notifications read',
    'project': 'Create project from request',
}

ME_ACTIONS = {
    'read': 'My profile',
    'partial_update': 'Update profile',
    'delete': 'Delete account',
}


class SectionAutoSchema(SwaggerAutoSchema):
    def get_tags(self, operation_keys=None):
        operation_keys = operation_keys or self.operation_keys
        section = operation_keys[1] if len(operation_keys) > 1 else operation_keys[0]
        if 'tasks' in operation_keys:
            section = 'tasks'
        return [TAG_NAMES.get(section, section)]

    def get_summary_and_description(self):
        summary, description = super().get_summary_and_description()
        if self.overrides.get('operation_summary'):
            return summary, description

        keys = self.operation_keys
        action, resource = keys[-1], keys[-2]
        if len(keys) > 2 and f'{keys[-3]}/{resource}' in NOUNS:
            resource = f'{keys[-3]}/{resource}'

        if resource in SPECIAL:
            return SPECIAL[resource], description
        if resource == 'me':
            return ME_ACTIONS.get(action, summary), description
        if resource in NOUNS:
            single, plural = NOUNS[resource]
            verbs = {
                'create': f'Add {single}',
                'read': f'Get {single}',
                'partial_update': f'Update {single}',
                'delete': f'Delete {single}',
            }
            if action == 'list':
                return f'List {plural}', description
            return verbs.get(action, summary), description
        return summary, description