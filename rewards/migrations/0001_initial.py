import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='MoonetixTransaction',
            fields=[
                ('transaction_id', models.CharField(max_length=191, primary_key=True, serialize=False)),
                ('wall_user_id', models.CharField(db_index=True, max_length=100)),
                ('reward_micro', models.BigIntegerField()),
                ('status', models.PositiveSmallIntegerField(choices=[(1, 'Credited'), (2, 'Reversed')], null=True)),
                ('offer_name', models.CharField(blank=True, default='', max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='Wallet',
            fields=[
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, serialize=False, to=settings.AUTH_USER_MODEL)),
                ('balance_micro', models.BigIntegerField(default=0)),
                ('age_confirmed_at', models.DateTimeField(blank=True, null=True)),
            ],
        ),
    ]
