from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_update_notification_model'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[('user', 'User'), ('author', 'Author')],
                default='user',
                max_length=20,
            ),
        ),
    ]
