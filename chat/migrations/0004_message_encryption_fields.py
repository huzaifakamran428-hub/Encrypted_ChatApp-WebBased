from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0003_group_groupmessage'),
    ]

    operations = [
        # Remove old message_content from Message
        migrations.RemoveField(model_name='message', name='message_content'),
        # Add encrypted fields to Message
        migrations.AddField(
            model_name='message',
            name='encrypted_content',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='message',
            name='encryption_iv',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='message',
            name='encrypted_file_path',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='message',
            name='file_iv',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        # Add encrypted fields to GroupMessage (replace message_content)
        migrations.RemoveField(model_name='groupmessage', name='message_content'),
        migrations.AddField(
            model_name='groupmessage',
            name='encrypted_content',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='groupmessage',
            name='encryption_iv',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
    ]
