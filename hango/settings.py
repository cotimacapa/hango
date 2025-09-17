# hango/settings.py
from pathlib import Path
import os

from dotenv import load_dotenv
import dj_database_url

# ── Paths & env ────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# ── Core config ────────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "unsafe-dev-key")
DEBUG = os.getenv("DEBUG", "1") == "1"
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]

# Optional: trust proxies / set CSRF origins via env (safe no-ops if unset)
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if os.getenv("USE_X_FORWARDED_PROTO", "0") == "1" else None

# ── Apps ──────────────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    "apps.accounts.apps.AccountsConfig",  # custom user app (must precede auth-related admin customizations)
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "apps.menu.apps.MenuConfig",
    "apps.orders",                        # if there is an AppConfig class, prefer "apps.orders.apps.OrdersConfig"
    "apps.classes.apps.ClassesConfig",
]

# ── Middleware ────────────────────────────────────────────────────────────────
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # LocaleMiddleware removed for single-language app
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "hango.urls"

# ── Templates ─────────────────────────────────────────────────────────────────
# Includes project-level templates/ (for admin widget templates) and app templates.
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],   # ← ensures templates/admin/widgets/weekday_mask.html is found
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.i18n",      # fine to keep
                "apps.orders.context_processors.cart_count",
                "apps.orders.context_processors.greeting",
            ],
        },
    },
]

WSGI_APPLICATION = "hango.wsgi.application"

# ── Database ──────────────────────────────────────────────────────────────────
DATABASES = {
    "default": dj_database_url.parse(
        os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
        conn_max_age=600,
        ssl_require=False,
    )
}

# ── Auth ──────────────────────────────────────────────────────────────────────
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ── i18n / tz (single-language: pt-BR) ────────────────────────────────────────
LANGUAGE_CODE = "pt-br"
LANGUAGES = [("pt-br", "Português (Brasil)")]
USE_I18N = True
USE_TZ = True
TIME_ZONE = "America/Belem"

# LOCALE_PATHS can be omitted entirely in single-language mode
# LOCALE_PATHS = [BASE_DIR / "locale"]

# ── Static files ──────────────────────────────────────────────────────────────
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]   # project-level static/ (e.g., hango/admin/weekday_mask.css)
STATIC_ROOT = BASE_DIR / "staticfiles"     # collectstatic target for production

# ── Auth flow ─────────────────────────────────────────────────────────────────
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/post-login/"
LOGOUT_REDIRECT_URL = "/"

# ── Django defaults ───────────────────────────────────────────────────────────
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
