"""Blueprint: админ-панель."""
import json

from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user

from extensions import db, csrf
from models import User, UsageRestriction, Notification, AdminMessage
from schedule import TIME_RE

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


def _schedule_list():
    items = UsageRestriction.query.order_by(UsageRestriction.id).all()
    return {"restrictions": [r.to_dict() for r in items]}


def _parse_schedule_payload(data, partial=False):
    """Валидация payload расписания. Возвращает (values, error)."""
    values = {}
    if not partial or "days" in data:
        days = data.get("days")
        if (not isinstance(days, list) or not days
                or not all(isinstance(d, int) and not isinstance(d, bool) and 0 <= d <= 6 for d in days)):
            return None, "Поле 'days' — непустой список чисел 0..6 (0=Пн)"
        values["days_json"] = json.dumps(sorted(set(days)))
    for field in ("start_time", "end_time"):
        if not partial or field in data:
            val = (data.get(field) or "").strip()
            if not TIME_RE.match(val):
                return None, f"Поле '{field}' — время в формате HH:MM"
            values[field] = val
    if not partial or "message" in data:
        msg = (data.get("message") or "").strip()
        if not msg:
            return None, "Поле 'message' обязательно — текст блокировки для пользователя"
        values["message"] = msg
    if "active" in data:
        values["active"] = bool(data.get("active"))
    return values, None


@admin.route("/api/admin/schedule", methods=["GET"])
@login_required
@admin_required
def api_schedule_list():
    return jsonify(_schedule_list())


@admin.route("/api/admin/schedule", methods=["POST"])
@login_required
@admin_required
@csrf.exempt
def api_schedule_add():
    data = request.get_json(silent=True) or {}
    values, error = _parse_schedule_payload(data)
    if error:
        return jsonify({"error": error}), 400
    item = UsageRestriction(
        days_json=values["days_json"],
        start_time=values["start_time"],
        end_time=values["end_time"],
        message=values["message"],
        active=values.get("active", True),
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({"ok": True, **_schedule_list()})


@admin.route("/api/admin/schedule/<int:rid>", methods=["PUT"])
@login_required
@admin_required
@csrf.exempt
def api_schedule_update(rid):
    item = db.session.get(UsageRestriction, rid)
    if item is None:
        return jsonify({"error": "Ограничение не найдено"}), 404
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"error": "Пустой запрос"}), 400
    values, error = _parse_schedule_payload(data, partial=True)
    if error:
        return jsonify({"error": error}), 400
    if "days_json" in values:
        item.days_json = values["days_json"]
    for field in ("start_time", "end_time", "message", "active"):
        if field in values:
            setattr(item, field, values[field])
    db.session.commit()
    return jsonify({"ok": True, **_schedule_list()})


@admin.route("/api/admin/schedule/<int:rid>", methods=["DELETE"])
@login_required
@admin_required
@csrf.exempt
def api_schedule_delete(rid):
    item = db.session.get(UsageRestriction, rid)
    if item is None:
        return jsonify({"error": "Ограничение не найдено"}), 404
    db.session.delete(item)
    db.session.commit()
    return jsonify({"ok": True, **_schedule_list()})


def _notification_list():
    items = Notification.query.order_by(Notification.created_at.desc()).all()
    return {"notifications": [n.to_dict() for n in items]}


@admin.route("/api/admin/notifications", methods=["GET"])
@login_required
@admin_required
def api_notifications_list():
    return jsonify(_notification_list())


@admin.route("/api/admin/notifications", methods=["POST"])
@login_required
@admin_required
@csrf.exempt
def api_notifications_add():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Поле 'text' обязательно"}), 400
    item = Notification(text=text)
    db.session.add(item)
    db.session.commit()
    return jsonify({"ok": True, **_notification_list()})


@admin.route("/api/admin/notifications/<int:nid>", methods=["DELETE"])
@login_required
@admin_required
@csrf.exempt
def api_notifications_delete(nid):
    item = db.session.get(Notification, nid)
    if item is None:
        return jsonify({"error": "Уведомление не найдено"}), 404
    from models import NotificationDismissed
    NotificationDismissed.query.filter_by(notification_id=nid).delete()
    db.session.delete(item)
    db.session.commit()
    return jsonify({"ok": True, **_notification_list()})


def _admin_message_list():
    items = AdminMessage.query.order_by(AdminMessage.is_read.asc(),
                                        AdminMessage.created_at.desc()).all()
    return {"messages": [m.to_dict() for m in items]}


@admin.route("/api/admin/messages", methods=["GET"])
@login_required
@admin_required
def api_admin_messages_list():
    return jsonify(_admin_message_list())


@admin.route("/api/admin/messages/<int:mid>/read", methods=["POST"])
@login_required
@admin_required
@csrf.exempt
def api_admin_message_read(mid):
    item = db.session.get(AdminMessage, mid)
    if item is None:
        return jsonify({"error": "Сообщение не найдено"}), 404
    data = request.get_json(silent=True) or {}
    item.is_read = bool(data.get("is_read", True))
    db.session.commit()
    return jsonify({"ok": True, **_admin_message_list()})


@admin.route("/api/admin/messages/<int:mid>", methods=["DELETE"])
@login_required
@admin_required
@csrf.exempt
def api_admin_message_delete(mid):
    item = db.session.get(AdminMessage, mid)
    if item is None:
        return jsonify({"error": "Сообщение не найдено"}), 404
    db.session.delete(item)
    db.session.commit()
    return jsonify({"ok": True, **_admin_message_list()})
