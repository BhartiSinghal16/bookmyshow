from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('movies', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='movie',
            name='trailer_url',
            field=models.URLField(
                blank=True,
                null=True,
                help_text='Paste a YouTube embed URL: https://www.youtube.com/embed/VIDEO_ID'
            ),
        ),
    ]