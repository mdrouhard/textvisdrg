# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('groups', '0005_group_include_types'),
    ]

    operations = [
        migrations.AddField(
            model_name='group',
            name='order',
            field=models.IntegerField(default=0),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='group',
            name='owner',
            field=models.ForeignKey(default=None, to=settings.AUTH_USER_MODEL, null=True),
            preserve_default=True,
        ),
    ]