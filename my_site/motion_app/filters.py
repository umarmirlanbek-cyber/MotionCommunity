from django_filters import rest_framework as filters
from .models import Task


class TaskFilter(filters.FilterSet):
    label = filters.CharFilter(method='filter_label')

    class Meta:
        model = Task
        fields = ['status', 'priority', 'type', 'assignee']

    def filter_label(self, queryset, name, value):
        return queryset.filter(labels__contains=[value])
