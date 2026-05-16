import os
import sys
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "chatapp.settings")

try:
    django.setup()
except Exception as e:
    print(f"[superuser] django.setup() failed: {e}")
    sys.exit(0)

try:
    from django.contrib.auth import get_user_model

    User = get_user_model()

    email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "")
    password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")

    # Find existing user by email and promote to superuser
    user = User.objects.get(email=email)
    user.is_staff = True
    user.is_superuser = True
    user.is_active = True
    user.set_password(password)
    user.save()
    print(f'[superuser] Promoted existing user "{user.username}" to superuser')

except User.DoesNotExist:
    print(f"[superuser] No user found with email {email}")
except Exception as e:
    print(f"[superuser] ERROR: {e}")

sys.exit(0)
