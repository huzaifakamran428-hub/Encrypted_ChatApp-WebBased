import mimetypes
import os

mimetypes.add_type("audio/webm", ".webm")
mimetypes.add_type("audio/ogg", ".ogg")
mimetypes.add_type("audio/ogg", ".oga")

"""
Django settings for chatapp project.
Web-Based Chat Application — SRS Project
"""

from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "SECRET_KEY", "django-insecure-chatapp-secret-key-change-in-production-2024"
)

DEBUG = os.environ.get("DEBUG", "True") == "True"

ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "users",
    "chat",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # 30-minute idle session timeout
    "chat.middleware.SessionIdleTimeoutMiddleware",
]

# ── Session / Security Settings ─────────────────────────────────────────────
# Session expires after 30 minutes of total time (hard maximum cookie age)
SESSION_COOKIE_AGE = 1800  # 30 minutes in seconds
# Keep session alive while user is active (reset age on every request)
SESSION_SAVE_EVERY_REQUEST = True
# How long (seconds) a user can be idle before being logged out (checked in middleware)
SESSION_IDLE_TIMEOUT = 1800  # 30 minutes

ROOT_URLCONF = "chatapp.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

ASGI_APPLICATION = "chatapp.asgi.application"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}

# ── MySQL Database ──────────────────────────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ.get("DB_NAME", "chatapp_db"),
        "USER": os.environ.get("DB_USER", "root"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "root"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "3306"),
        "CONN_MAX_AGE": 60,  # ← reuse connections for 60s
        "CONN_HEALTH_CHECKS": True,  # ← test connection before reuse
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            "connect_timeout": 10,
        },
    }
}
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Karachi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "users.CustomUser"

LOGIN_URL = "/users/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/users/login/"

CSRF_TRUSTED_ORIGINS = [
    "https://*.trycloudflare.com",
    "https://*.ngrok-free.app",
    "https://*.railway.app",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

# ── Email via Resend (works on Railway — uses HTTPS not blocked SMTP) ───────
EMAIL_BACKEND = "anymail.backends.resend.EmailBackend"

ANYMAIL = {
    "RESEND_API_KEY": os.environ.get(
        "RESEND_API_KEY", "re_As9PF6i8_84diJFTvqaeJ6v9pawycVrRX"
    ),
}

DEFAULT_FROM_EMAIL = "ChatApp <noreply@huzaifakamran.site>"

EMAIL_TIMEOUT = 10
OTP_EXPIRY_MINUTES = 10

DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024 * 1024  # 5 GB
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024 * 1024  # 5 GB
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000

# Use temp file for large uploads (avoids RAM exhaustion)
FILE_UPLOAD_HANDLERS = [
    "django.core.files.uploadhandler.TemporaryFileUploadHandler",
]

# ── AES-256 Encryption Key ──────────────────────────────────────────────────
# 32 bytes = 256 bits for AES-256
# KEEP THIS SECRET — never commit to version control in production
# Change this key if deploying publicly
ENCRYPTION_KEY = os.environ.get(
    "ENCRYPTION_KEY", "a135f6fe48b411c866a5ada73cdee58b053dc185f281cd732bef6ce88a21f77e"
)
