from django_filters import rest_framework as filters
from .choices import PositionChoices
from .models import Task


class MemberFilter(filters.FilterSet):
    position = filters.ChoiceFilter(choices=PositionChoices.choices, method='filter_position')

    def filter_position(self, queryset, name, value):
        return queryset.filter(positions__contains=[value])


class TaskFilter(filters.FilterSet):
    label = filters.CharFilter(method='filter_label')

    class Meta:
        model = Task
        fields = ['status', 'priority', 'type', 'assignee']

    def filter_label(self, queryset, name, value):
        return queryset.filter(labels__contains=[value])


class MyTaskFilter(TaskFilter):
    class Meta(TaskFilter.Meta):
        fields = ['status', 'priority', 'type']
