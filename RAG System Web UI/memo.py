"""Blueprint: мастер создания мемо."""
import json

from flask import Blueprint, request, jsonify, send_file
from flask_login import login_required, current_user

import memo_docx

from extensions import csrf, db
from models import MemoState

memo = Blueprint("memo", __name__)


@memo.route("/api/memo/template", methods=["GET"])
@login_required
def api_memo_template():
    info = memo_docx.get_template_info()
    return jsonify({
        "fields": [
            {
                "key": key,
                "label": memo_docx.FIELD_LABELS.get(key, key.replace("_", " ").title()),
                "hint": memo_docx.FIELD_HINTS.get(key, ""),
            }
            for key in info["fields"]
        ],
        "path": info["path"],
        "updated": info["updated"],
    })


@memo.route("/api/memo/state", methods=["GET"])
@login_required
def api_memo_state_get():
    st = MemoState.query.filter_by(user_id=current_user.id).first()
    return jsonify({"state": st.to_dict() if st else {}})


@memo.route("/api/memo/state", methods=["POST"])
@login_required
@csrf.exempt
def api_memo_state_save():
    data = request.get_json(silent=True) or {}
    state = data.get("state")
    if not isinstance(state, dict):
        return jsonify({"error": "Поле 'state' обязательно"}), 400
    st = MemoState.query.filter_by(user_id=current_user.id).first()
    if st is None:
        st = MemoState(user_id=current_user.id)
        db.session.add(st)
    st.state_json = json.dumps(state, ensure_ascii=False)
    db.session.commit()
    return jsonify({"ok": True})


@memo.route("/api/memo/state", methods=["DELETE"])
@login_required
@csrf.exempt
def api_memo_state_clear():
    st = MemoState.query.filter_by(user_id=current_user.id).first()
    if st is not None:
        db.session.delete(st)
        db.session.commit()
    return jsonify({"ok": True})


@memo.route("/api/memo/docx", methods=["POST"])
@login_required
@csrf.exempt
def api_memo_docx():
    data = request.get_json(silent=True) or {}
    try:
        buf = memo_docx.generate_memo_docx(data)
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return send_file(
        buf,
        as_attachment=True,
        download_name="sluzhebnaya_zapiska.docx",
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@memo.route("/api/admin/memo/template/reload", methods=["POST"])
@login_required
@csrf.exempt
def api_admin_memo_template_reload():
    if not current_user.is_admin:
        return jsonify({"error": "Доступно только администратору"}), 403
    fields = memo_docx.reload_template_fields()
    return jsonify({
        "ok": True,
        "fields": fields,
        "path": memo_docx.TEMPLATE_PATH,
        "updated": memo_docx.get_template_info()["updated"],
    })


@memo.route("/api/admin/memo/template", methods=["POST"])
@login_required
@csrf.exempt
def api_admin_memo_template_upload():
    if not current_user.is_admin:
        return jsonify({"error": "Доступно только администратору"}), 403
    if "file" not in request.files:
        return jsonify({"error": "Файл не передан (поле 'file')"}), 400
    file = request.files["file"]
    if not file.filename or not file.filename.lower().endswith(".dotx"):
        return jsonify({"error": "Нужен файл шаблона .dotx"}), 400
    fields = memo_docx.save_template_file(file.read())
    return jsonify({
        "ok": True,
        "fields": fields,
        "path": memo_docx.TEMPLATE_PATH,
        "updated": memo_docx.get_template_info()["updated"],
    })
