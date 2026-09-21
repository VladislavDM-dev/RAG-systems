"""Инициализация расширений Flask."""
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

login_manager.login_view = "auth.login_page"
login_manager.login_message = "Войдите в систему"
login_manager.login_message_category = "warning"
