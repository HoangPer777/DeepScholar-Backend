from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0004_alter_user_role"),
    ]

    operations = [
        migrations.AddField(
            model_name="author",
            name="article_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="author",
            name="like_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="author",
            name="commenter_count",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
