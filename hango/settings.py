import os
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')
SECRET_KEY = os.getenv('SECRET_KEY','unsafe-dev-key')
DEBUG = os.getenv('DEBUG','1')=='1'
ALLOWED_HOSTS=[h.strip() for h in os.getenv('ALLOWED_HOSTS','localhost,127.0.0.1').split(',')]
INSTALLED_APPS=['django.contrib.admin','django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles','apps.menu','apps.orders']
MIDDLEWARE=['django.middleware.security.SecurityMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware','django.contrib.messages.middleware.MessageMiddleware','django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF='hango.urls'
TEMPLATES=[{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[BASE_DIR/'templates'],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.debug','django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages','apps.orders.context_processors.cart_count']}}]
WSGI_APPLICATION='hango.wsgi.application'
DATABASES={'default': dj_database_url.parse(os.getenv('DATABASE_URL', f"sqlite:///{BASE_DIR / 'db.sqlite3'}"), conn_max_age=600, ssl_require=False)}
AUTH_PASSWORD_VALIDATORS=[{'NAME':'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},{'NAME':'django.contrib.auth.password_validation.MinimumLengthValidator'},{'NAME':'django.contrib.auth.password_validation.CommonPasswordValidator'},{'NAME':'django.contrib.auth.password_validation.NumericPasswordValidator'}]
LANGUAGE_CODE='en-us'
TIME_ZONE='America/Belem'
USE_I18N=True
USE_TZ=True
STATIC_URL='/static/'
STATICFILES_DIRS=[BASE_DIR/'static']
STATIC_ROOT=BASE_DIR/'staticfiles'
DEFAULT_AUTO_FIELD='django.db.models.BigAutoField'

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'     # where to go after successful login
LOGOUT_REDIRECT_URL = '/'    # where to go after logout


