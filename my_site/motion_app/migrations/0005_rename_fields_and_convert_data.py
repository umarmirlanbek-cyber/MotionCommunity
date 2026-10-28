from django.db import migrations, models


def convert_data(apps, schema_editor):
    UserProfile = apps.get_model('motion_app', 'UserProfile')
    TeamMember = apps.get_model('motion_app', 'TeamMember')
    ProjectMember = apps.get_model('motion_app', 'ProjectMember')
    Education = apps.get_model('motion_app', 'Education')
    Language = apps.get_model('motion_app', 'Language')
    ClientRequest = apps.get_model('motion_app', 'ClientRequest')

    UserProfile.objects.filter(models.Q(is_superuser=True) | models.Q(role='Admin')).update(
        role='Admin', is_staff=True, is_superuser=True
    )
    UserProfile.objects.filter(is_superuser=False).update(role='Member', is_staff=False)
    UserProfile.objects.filter(position='UI/UX_Designer').update(position='UI_UX_Designer')

    TeamMember.objects.filter(role='Developer').update(role='Member')
    ProjectMember.objects.filter(role='Developer').update(role='Member')
    Language.objects.filter(level='Родной язык').update(level='Native')

    for education in Education.objects.all():
        education.start_year_number = education.start_year.year
        education.end_year_number = education.end_year.year if education.end_year else None
        education.save(update_fields=['start_year_number', 'end_year_number'])

    for client_request in ClientRequest.objects.all():
        client_request.title = client_request.title_ru or client_request.title_en or client_request.title
        client_request.description = (
            client_request.description_ru or client_request.description_en or client_request.description
        )
        client_request.save(update_fields=['title', 'description'])


class Migration(migrations.Migration):

    dependencies = [
        ('motion_app', '0004_project_team'),
    ]

    operations = [
        migrations.RenameModel('Languages', 'Language'),
        migrations.RenameModel('Certificates', 'Certificate'),

        migrations.RenameField('team', 'team_name', 'name'),
        migrations.RenameField('team', 'team_image', 'image'),
        migrations.RenameField('project', 'project_status', 'status'),
        migrations.RenameField('project', 'preview_image', 'image'),
        migrations.RenameField('workexperience', 'start_time', 'start_date'),
        migrations.RenameField('workexperience', 'end_time', 'end_date'),
        migrations.RenameField('education', 'educational_institution', 'institution'),
        migrations.RenameField('education', 'responsibilities', 'description'),
        migrations.RenameField('language', 'Level', 'level'),
        migrations.RenameField('language', 'languages', 'name'),
        migrations.RenameField('certificate', 'given_date', 'issue_date'),
        migrations.RenameField('certificate', 'text', 'description'),
        migrations.RenameField('certificate', 'certificate_image', 'image'),

        migrations.AddField(
            model_name='education',
            name='start_year_number',
            field=models.PositiveSmallIntegerField(default=0),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='education',
            name='end_year_number',
            field=models.PositiveSmallIntegerField(null=True, blank=True),
        ),

        migrations.RunPython(convert_data, migrations.RunPython.noop),

        migrations.RemoveField('education', 'start_year'),
        migrations.RemoveField('education', 'end_year'),
        migrations.RenameField('education', 'start_year_number', 'start_year'),
        migrations.RenameField('education', 'end_year_number', 'end_year'),

        migrations.RemoveField('clientrequest', 'title_ru'),
        migrations.RemoveField('clientrequest', 'title_en'),
        migrations.RemoveField('clientrequest', 'description_ru'),
        migrations.RemoveField('clientrequest', 'description_en'),
    ]
