from django.conf import settings
from django.utils import translation


class APILanguageMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.allowed = {code for code, _ in getattr(settings, 'LANGUAGES', [])}

    def __call__(self, request):
        parts = request.path_info.strip('/').split('/')

        lang = None
        if len(parts) >= 2 and parts[0] == 'api' and parts[1] in self.allowed:
            lang = parts[1]

        if lang:
            translation.activate(lang)
            request.LANGUAGE_CODE = lang

        response = self.get_response(request)

        if lang:
            response['Content-Language'] = lang

        return response
