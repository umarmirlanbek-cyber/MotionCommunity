from modeltranslation.translator import TranslationOptions, register
from .models import UserProfile, Team, Project


@register(UserProfile)
class UserProfileTranslationOptions(TranslationOptions):
    fields = ('bio',)


@register(Team)
class TeamTranslationOptions(TranslationOptions):
    fields = ('description',)


@register(Project)
class ProjectTranslationOptions(TranslationOptions):
    fields = ('description',)
