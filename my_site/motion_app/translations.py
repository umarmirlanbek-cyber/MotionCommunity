from modeltranslation.translator import TranslationOptions, register
from .models import UserProfile, Team, Project, ClientRequest


@register(UserProfile)
class UserProfileTranslationOptions(TranslationOptions):
    fields = ('bio',)


@register(Team)
class TeamTranslationOptions(TranslationOptions):
    fields = ('description',)


@register(Project)
class ProjectTranslationOptions(TranslationOptions):
    fields = ('description',)


@register(ClientRequest)
class ClientRequestTranslationOptions(TranslationOptions):
    fields = ('title', 'description',)