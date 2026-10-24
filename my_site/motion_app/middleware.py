from django.conf import settings
from django.utils import translation


class APILanguageMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.allowed = {code for code, _ in settings.LANGUAGES}

    def __call__(self, request):
        parts = request.path_info.strip('/').split('/')

        lang = None
        if len(parts) >= 2 and parts[0] == 'api' and parts[1] in self.allowed:
            lang = parts[1]

        translation.activate(lang or settings.LANGUAGE_CODE)

        response = self.get_response(request)

        if lang:
            response['Content-Language'] = lang
        translation.deactivate()

        return response
