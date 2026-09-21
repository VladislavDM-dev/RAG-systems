"""RAG System Web UI — Flask + SQLite."""
import os
import sys
import logging

from flask import Flask, jsonify, redirect, url_for

from config import Config
from extensions import db, login_manager, csrf
from models import User
from api_client import RAGClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.json.ensure_ascii = False

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    app.rag = RAGClient(app.config["RAG_API_URL"])

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from auth import auth
    from chat import chat
    from memo import memo
    from admin import admin

    app.register_blueprint(auth)
    app.register_blueprint(chat)
    app.register_blueprint(memo)
    app.register_blueprint(admin)

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not found"}), 404

    with app.app_context():
        os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"), exist_ok=True)
        db.create_all()
        _seed_admin(app)

    return app


def _seed_admin(app):
    admin_user = User.query.filter_by(username="admin").first()
    if not admin_user:
        admin_user = User(username="admin", role="admin")
        admin_user.set_password(app.config["DEFAULT_ADMIN_PASSWORD"])
        db.session.add(admin_user)
        db.session.commit()
        print(f"[auth] Создан пользователь admin (пароль: {app.config['DEFAULT_ADMIN_PASSWORD']})")


app = create_app()

if __name__ == "__main__":
    port = app.config["PORT"]
    rag_url = app.config["RAG_API_URL"]
    print(f"RAG System Web UI: http://127.0.0.1:{port}  ->  API {rag_url}")
    print("   Порт 80 может требовать прав администратора.")
    app.run(debug=False, host="0.0.0.0", port=port, use_reloader=False)
