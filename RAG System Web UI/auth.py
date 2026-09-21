"""Blueprint: аутентификация."""
import re

from flask import Blueprint, render_template, redirect, request, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user

from extensions import db, csrf
from models import User

auth = Blueprint("auth", __name__)


@auth.route("/login", methods=["GET"])
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for("chat.index"))
    return render_template("auth/login.html")


@auth.route("/login", methods=["POST"])
def login_submit():
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    next_url = request.form.get("next") or "/"

    user = User.query.filter_by(username=username).first()
    if user and user.check_password(password):
        login_user(user)
        safe = next_url if next_url.startswith("/") else "/"
        return redirect(safe)

    flash("Неверный логин или пароль", "danger")
    return render_template("auth/login.html", next_url=next_url)


@auth.route("/register", methods=["GET"])
def register_page():
    if current_user.is_authenticated:
        return redirect(url_for("chat.index"))

    from flask import current_app
    if not current_app.config.get("OPEN_REGISTRATION", True):
        flash("Регистрация отключена", "warning")
        return redirect(url_for("auth.login_page"))

    return render_template("auth/register.html")


@auth.route("/register", methods=["POST"])
def register_submit():
    from flask import current_app
    if not current_app.config.get("OPEN_REGISTRATION", True):
        flash("Регистрация отключена", "warning")
        return redirect(url_for("auth.login_page"))

    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    password2 = request.form.get("password2") or ""

    if password != password2:
        flash("Пароли не совпадают", "danger")
        return render_template("auth/register.html", username=username)

    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", username):
        flash("Логин: 3-32 символа, только буквы, цифры, точка, дефис, подчёркивание", "danger")
        return render_template("auth/register.html", username=username)

    if len(password) < 6:
        flash("Пароль должен быть не короче 6 символов", "danger")
        return render_template("auth/register.html", username=username)

    if User.query.filter_by(username=username).first():
        flash("Такой логин уже существует", "danger")
        return render_template("auth/register.html", username=username)

    user = User(username=username, role="user")
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    login_user(user)
    return redirect(url_for("chat.index"))


@auth.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login_page"))
