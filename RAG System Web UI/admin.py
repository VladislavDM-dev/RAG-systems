"""Blueprint: админ-панель."""
from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user

from extensions import db, csrf
from models import User

admin = Blueprint("admin", __name__)


def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return jsonify({"error": "Доступно только администратору"}), 403
        return f(*args, **kwargs)
    return decorated


@admin.route("/admin")
@login_required
@admin_required
def admin_page():
    rag = current_app.rag
    status = rag.engine_status()
    cfg = rag.get_config()
    models = rag.list_models().get("models") or {}
    info = rag.info()

    return render_template("admin/index.html",
                           user=current_user,
                           version=status.get("version", "—"),
                           document_count=status.get("document_count", 0),
                           index_updated=status.get("index_updated", "—"),
                           provider=cfg.get("provider", "ollama"),
                           llm=cfg.get("llm", ""),
                           llm_embed=cfg.get("llm_embed", ""),
                           llm_keywords=cfg.get("llm_keywords", ""),
                           context_window=cfg.get("context_window", 4096),
                           chunk_size=cfg.get("chunk_size", 256),
                           chunk_overlap=cfg.get("chunk_overlap", 50),
                           similarity_top_k=cfg.get("similarity_top_k", 10),
                           llm_url=cfg.get("url", ""),
                           api_key=cfg.get("api_key", ""),
                           llm_thinking=models.get("thinking", []),
                           llm_embedding=models.get("embedding", []),
                           llm_all=models.get("all", []))


@admin.route("/api/admin/info", methods=["GET"])
@login_required
@admin_required
def api_admin_info():
    rag = current_app.rag
    status = rag.engine_status()
    info = rag.info()
    return jsonify({
        "version": status.get("version", "—"),
        "document_count": status.get("document_count", 0),
        "index_updated": status.get("index_updated", "—"),
        "is_initialized": status.get("is_initialized", False),
        "is_syncing": status.get("is_syncing", False),
        "status": status.get("status", ""),
        "progress": status.get("progress", 0),
        "sync_files": status.get("sync_files", []),
        "status_backend": info.get("status_backend", False),
        "provider": info.get("provider", ""),
    })


@admin.route("/api/admin/config", methods=["GET"])
@login_required
@admin_required
def api_admin_config():
    rag = current_app.rag
    return jsonify(rag.get_config())


@admin.route("/api/admin/config", methods=["PATCH"])
@login_required
@admin_required
@csrf.exempt
def api_admin_config_update():
    rag = current_app.rag
    data = request.get_json(silent=True) or {}
    result = rag.patch_config(**data)
    return jsonify(result)


@admin.route("/api/admin/config/reset", methods=["POST"])
@login_required
@admin_required
@csrf.exempt
def api_admin_config_reset():
    rag = current_app.rag
    return jsonify(rag.reset_config())


@admin.route("/api/admin/models", methods=["GET"])
@login_required
@admin_required
def api_admin_models():
    rag = current_app.rag
    return jsonify(rag.list_models())


@admin.route("/api/admin/provider", methods=["GET"])
@login_required
@admin_required
def api_admin_provider():
    rag = current_app.rag
    return jsonify(rag.get_provider())


@admin.route("/api/admin/provider", methods=["POST"])
@login_required
@admin_required
@csrf.exempt
def api_admin_provider_set():
    rag = current_app.rag
    data = request.get_json(silent=True) or {}
    provider = data.get("provider", "")
    return jsonify(rag.set_provider(provider))


@admin.route("/api/admin/folders", methods=["GET"])
@login_required
@admin_required
def api_admin_folders():
    rag = current_app.rag
    return jsonify({"folders": rag.get_folders()})


@admin.route("/api/admin/folders", methods=["POST"])
@login_required
@admin_required
@csrf.exempt
def api_admin_folders_set():
    rag = current_app.rag
    data = request.get_json(silent=True) or {}
    folders = data.get("folders", [])
    return jsonify(rag.set_folders(folders))


@admin.route("/api/admin/sync", methods=["POST"])
@login_required
@admin_required
@csrf.exempt
def api_admin_sync():
    rag = current_app.rag
    data = request.get_json(silent=True) or {}
    reset = data.get("reset", False)
    return jsonify(rag.trigger_sync(reset=reset))


@admin.route("/api/admin/users", methods=["GET"])
@login_required
@admin_required
def api_users_list():
    users = User.query.all()
    return jsonify({"users": [u.to_dict() for u in users]})


@admin.route("/api/admin/users", methods=["POST"])
@login_required
@admin_required
@csrf.exempt
def api_users_add():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    import re
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", username):
        return jsonify({"error": "Логин: 3-32 символа, только буквы, цифры, точка, дефис, подчёркивание"}), 400
    if len(password) < 6:
        return jsonify({"error": "Пароль должен быть не короче 6 символов"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Такой логин уже существует"}), 400

    user = User(username=username, role="user")
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    users = User.query.all()
    return jsonify({"ok": True, "users": [u.to_dict() for u in users]})


@admin.route("/api/admin/users/<int:uid>", methods=["DELETE"])
@login_required
@admin_required
@csrf.exempt
def api_users_delete(uid):
    user = User.query.get_or_404(uid)
    if user.is_admin:
        return jsonify({"error": "Нельзя удалить администратора"}), 400
    db.session.delete(user)
    db.session.commit()
    users = User.query.all()
    return jsonify({"ok": True, "users": [u.to_dict() for u in users]})


@admin.route("/api/admin/users/<int:uid>/password", methods=["PUT"])
@login_required
@admin_required
@csrf.exempt
def api_users_set_password(uid):
    user = User.query.get_or_404(uid)
    data = request.get_json(silent=True) or {}
    password = data.get("password") or ""
    if len(password) < 6:
        return jsonify({"error": "Пароль должен быть не короче 6 символов"}), 400
    user.set_password(password)
    db.session.commit()
    users = User.query.all()
    return jsonify({"ok": True, "users": [u.to_dict() for u in users]})
