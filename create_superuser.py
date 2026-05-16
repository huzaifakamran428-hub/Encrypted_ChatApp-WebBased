import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "chatapp.settings")
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "admin")
email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "admin@example.com")
password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "Admin@1234")

try:
    user = User.objects.get(username=username)
    # User exists — force reset password and ensure superuser flags are set
    user.set_password(password)
    user.is_staff = True
    user.is_superuser = True
    user.email = email
    user.save()
    print(f"[superuser] Password reset for existing user: {username}")

except User.DoesNotExist:
    User.objects.create_superuser(
        username=username,
        email=email,
        password=password,
    )
    print(f"[superuser] Created new superuser: {username}")

except Exception as e:
    print(f"[superuser] ERROR: {e}")
