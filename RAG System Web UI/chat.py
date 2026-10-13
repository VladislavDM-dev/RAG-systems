"""Blueprint: чат и история."""
import json

from flask import Blueprint, render_template, request, jsonify, Response, current_app
from flask_login import login_required, current_user

from extensions import db, csrf
from models import Conversation, Message, Favorite, Notification, NotificationDismissed, AdminMessage
from schedule import get_restriction_message

chat = Blueprint("chat", __name__)


@chat.route("/")
@login_required
def index():
    return render_template("chat/index.html", user=current_user)


@chat.route("/api/chat/stream", methods=["POST"])
@login_required
@csrf.exempt
def api_chat_stream():
    block = get_restriction_message(current_user)
    if block:
        return jsonify({"error": block, "restricted": True}), 403

    data = request.get_json(silent=True) or {}
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "Поле 'prompt' обязательно"}), 400

    system_prompt = data.get("system_prompt")
    explicit_system_prompt = system_prompt is not None
    rag = current_app.rag

    if prompt.lower().startswith(current_app.config["COMMAND_CREATE"].lower()):
        if not system_prompt:
            system_prompt = current_app.config["SYSTEM_PROMPT_MEMO"]
    else:
        if not system_prompt:
            system_prompt = current_app.config["SYSTEM_PROMPT_RAG"]

    if data.get("memos_paged"):
        temperature = data.get("temperature")
        if temperature is None:
            temperature = 0.2
        return Response(
            _stream_memos(rag, prompt, temperature),
            mimetype="text/event-stream",
        )

    # Авто-детекция поиска записок срабатывает только для обычных вопросов:
    # если клиент задал явный system_prompt (мастер записки), промпт содержит
    # слово «записка», и поиск не должен перехватывать генерацию вариантов.
    if not explicit_system_prompt:
        auto_topic = detect_memos_topic(prompt)
        if auto_topic:
            return Response(
                _stream_memos(rag, auto_topic, 0.0),
                mimetype="text/event-stream",
            )

    def generate():
        sources = []
        full_answer = ""
        full_reasoning = ""
        for event in rag.stream_chat(prompt, system_prompt=system_prompt,
                                     top_k=data.get("top_k"),
                                     temperature=data.get("temperature")):
            if event.get("type") == "sources":
                sources = event.get("data", [])
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            elif event.get("type") == "reasoning":
                full_reasoning += event.get("data", "")
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            elif event.get("type") == "token":
                full_answer += event.get("data", "")
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            elif event.get("type") == "done":
                if not full_answer:
                    full_answer = event.get("answer", "")
                merged_sources = event.get("sources") or sources
                final = {
                    "type": "done",
                    "answer": full_answer,
                    "reasoning": full_reasoning or event.get("reasoning", ""),
                    "sources": _dedupe_sources(merged_sources),
                    "prompt": prompt,
                    "tokens_in": event.get("tokens_in"),
                    "tokens_out": event.get("tokens_out"),
                    "elapsed": event.get("elapsed"),
                }
                yield f"data: {json.dumps(final, ensure_ascii=False)}\n\n"
            elif event.get("type") == "error":
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return Response(generate(), mimetype="text/event-stream")


_MEMO_MARKER_PREFIXES = ("служебн", "записк", "мемо", "служебк")
_MEMO_QUESTION_PREFIXES = ("что такое", "что значит", "зачем нужн", "как составить",
                           "как написать", "как оформить", "какие бывают", "виды")
_MEMO_STOPWORDS = (
    "найди", "найти", "поиск", "поискать", "покажи", "покажите", "подбери",
    "подобрать", "дай", "выдай", "все", "всех", "нужно", "нужны", "нужна",
    "сегодня", "для", "о", "об", "по", "про", "на", "и", "теме", "тему",
    "тема", "список", "списком", "какие", "есть", "имеются",
)


def detect_memos_topic(prompt: str):
    """Определяет по тексту запроса, идёт ли поиск служебных записок.

    Возвращает тему (подстроку запроса) если намерение подтверждено
    словами-маркерами, иначе None. Явные вопросы о сути («что такое
    служебная записка») в поиск не уходят.
    """
    if not prompt:
        return None
    low = prompt.strip().lower()
    if any(low.startswith(p) for p in _MEMO_QUESTION_PREFIXES):
        return None
    has_marker = any(p in low for p in _MEMO_MARKER_PREFIXES)
    if not has_marker:
        return None
    words = low.replace(",", " ").replace(".", " ").split()
    topic_words = []
    for w in words:
        w = w.strip("-:;!?")
        if not w:
            continue
        if any(w.startswith(p) for p in _MEMO_MARKER_PREFIXES):
            continue
        if w in _MEMO_STOPWORDS:
            continue
        topic_words.append(w)
    topic = " ".join(topic_words)
    if not topic:
        return None
    return topic


def _dedupe_sources(sources):
    seen = {}
    for src in sources or []:
        key = src.get("file_path") or src.get("file_name") or ""
        if not key:
            continue
        if key not in seen or float(src.get("score") or 0) > float(seen[key].get("score") or 0):
            seen[key] = src
    return list(seen.values())


def _memos_answer(documents, prompt):
    """Собирает итоговый ответ по документам: название, ссылка, полный текст."""
    if not documents:
        return "Релевантные служебные записки по теме не найдены."

    lines = []
    for doc in documents:
        name = doc.get("file_name") or doc.get("file_path") or ""
        path = doc.get("file_path") or ""
        text = (doc.get("text") or "").strip() or "_Документ пуст._"
        lines.append(f"### {name}")
        lines.append(f"Документ: `{path}`")
        lines.append("")
        lines.append(text)
        lines.append("")
    full = "\n".join(lines).strip()
    return f"{full}\n\n**Итого записок по теме: {len(documents)}**"


def _stream_memos(rag, prompt, temperature):
    """Поиск всех записок по теме через ядро: стримится reasoning батч-LLM,
    в конце — события done с документами (название, полный путь, полный текст)."""
    def emit(payload):
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    # Предпочитаем потоковый endpoint ядра (reasoning), иначе — fallback.
    if hasattr(rag, "memos_stream"):
        try:
            documents = []
            full_reasoning = []
            metrics = {}
            for event in rag.memos_stream(prompt, temperature=temperature):
                etype = event.get("type")
                if etype == "error":
                    yield emit({"type": "error", "data": event.get("data", "Ошибка")})
                    return
                if etype == "reasoning":
                    part = event.get("data", "")
                    full_reasoning.append(part)
                    yield emit({"type": "reasoning", "data": part})
                if etype == "done":
                    documents = event.get("documents") or []
                    for key in ("tokens_in", "tokens_out", "elapsed"):
                        if event.get(key) is not None:
                            metrics[key] = event.get(key)
            yield emit({
                "type": "done",
                "answer": _memos_answer(documents, prompt),
                "documents": documents,
                "reasoning": "".join(full_reasoning),
                "prompt": prompt,
                "tokens_in": metrics.get("tokens_in"),
                "tokens_out": metrics.get("tokens_out"),
                "elapsed": metrics.get("elapsed"),
            })
            return
        except Exception as e:
            yield emit({"type": "error", "data": str(e)})
            return

    try:
        result = rag.memos(prompt, temperature=temperature)
    except Exception as e:
        yield emit({"type": "error", "data": str(e)})
        return

    if not result:
        yield emit({"type": "error", "data": "Ядро не ответило."})
        return
    if result.get("error"):
        yield emit({"type": "error", "data": result["error"]})
        return

    documents = result.get("documents") or []
    yield emit({
        "type": "done",
        "answer": _memos_answer(documents, prompt),
        "documents": documents,
        "prompt": prompt,
    })


@chat.route("/api/conversations", methods=["GET"])
@login_required
def api_conversations_list():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    convs = Conversation.query.filter_by(user_id=current_user.id) \
        .order_by(Conversation.updated_at.desc()) \
        .paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "conversations": [c.to_dict() for c in convs.items],
        "total": convs.total,
        "pages": convs.pages,
        "page": page,
    })


@chat.route("/api/conversations", methods=["POST"])
@login_required
@csrf.exempt
def api_conversations_create():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "Новый диалог").strip()
    conv = Conversation(user_id=current_user.id, title=title)
    db.session.add(conv)
    db.session.commit()
    return jsonify({"ok": True, "conversation": conv.to_dict()})


@chat.route("/api/conversations/<int:cid>", methods=["GET"])
@login_required
def api_conversations_get(cid):
    conv = Conversation.query.filter_by(id=cid, user_id=current_user.id).first_or_404()
    messages = conv.messages.all()
    return jsonify({
        "conversation": conv.to_dict(),
        "messages": [m.to_dict() for m in messages],
    })


@chat.route("/api/conversations/<int:cid>", methods=["PUT"])
@login_required
@csrf.exempt
def api_conversations_update(cid):
    conv = Conversation.query.filter_by(id=cid, user_id=current_user.id).first_or_404()
    data = request.get_json(silent=True) or {}
    if "title" in data:
        conv.title = data["title"]
    db.session.commit()
    return jsonify({"ok": True, "conversation": conv.to_dict()})


@chat.route("/api/conversations/<int:cid>", methods=["DELETE"])
@login_required
@csrf.exempt
def api_conversations_delete(cid):
    conv = Conversation.query.filter_by(id=cid, user_id=current_user.id).first_or_404()
    db.session.delete(conv)
    db.session.commit()
    return jsonify({"ok": True})


@chat.route("/api/messages", methods=["POST"])
@login_required
@csrf.exempt
def api_messages_create():
    data = request.get_json(silent=True) or {}
    conv_id = data.get("conversation_id")
    role = data.get("role")
    content = data.get("content", "")

    if not conv_id or not role:
        return jsonify({"error": "conversation_id и role обязательны"}), 400

    conv = Conversation.query.filter_by(id=conv_id, user_id=current_user.id).first_or_404()

    msg = Message(
        conversation_id=conv.id,
        role=role,
        content=content,
        sources_json=json.dumps(data.get("sources")) if data.get("sources") else None,
        memo_data_json=json.dumps(data.get("memo_data")) if data.get("memo_data") else None,
    )
    db.session.add(msg)

    if not data.get("skip_touch"):
        from datetime import datetime
        conv.updated_at = datetime.utcnow()

    db.session.commit()
    return jsonify({"ok": True, "message": msg.to_dict()})


@chat.route("/api/favorites", methods=["GET"])
@login_required
def api_favorites_list():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    favs = Favorite.query.filter_by(user_id=current_user.id) \
        .order_by(Favorite.created_at.desc()) \
        .paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "favorites": [f.to_dict() for f in favs.items],
        "total": favs.total,
        "pages": favs.pages,
        "page": page,
    })


@chat.route("/api/favorites", methods=["POST"])
@login_required
@csrf.exempt
def api_favorites_create():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    content = (data.get("content") or "").strip()
    if not title or not content:
        return jsonify({"error": "title и content обязательны"}), 400

    fav = Favorite(
        user_id=current_user.id,
        title=title,
        content=content,
        sources_json=json.dumps(data.get("sources")) if data.get("sources") else None,
        memo_data_json=json.dumps(data.get("memo_data")) if data.get("memo_data") else None,
    )
    db.session.add(fav)
    db.session.commit()
    return jsonify({"ok": True, "favorite": fav.to_dict()})


@chat.route("/api/favorites/<int:fid>", methods=["DELETE"])
@login_required
@csrf.exempt
def api_favorites_delete(fid):
    fav = Favorite.query.filter_by(id=fid, user_id=current_user.id).first_or_404()
    db.session.delete(fav)
    db.session.commit()
    return jsonify({"ok": True})


@chat.route("/api/status", methods=["GET"])
@login_required
def api_status():
    data = current_app.rag.index_status()
    block = get_restriction_message(current_user)
    data["restricted"] = bool(block)
    data["restriction_message"] = block or ""
    return jsonify(data)


@chat.route("/api/notifications", methods=["GET"])
@login_required
def api_notifications():
    dismissed = {
        d.notification_id
        for d in NotificationDismissed.query.filter_by(user_id=current_user.id)
    }
    items = [
        n.to_dict()
        for n in Notification.query.order_by(Notification.created_at.desc()).all()
        if n.id not in dismissed
    ]
    return jsonify({"notifications": items})


@chat.route("/api/notifications/<int:nid>/dismiss", methods=["POST"])
@login_required
@csrf.exempt
def api_notification_dismiss(nid):
    item = db.session.get(Notification, nid)
    if item is None:
        return jsonify({"error": "Уведомление не найдено"}), 404
    existing = NotificationDismissed.query.filter_by(
        user_id=current_user.id, notification_id=nid
    ).first()
    if existing is None:
        db.session.add(NotificationDismissed(user_id=current_user.id, notification_id=nid))
        db.session.commit()
    return jsonify({"ok": True})


@chat.route("/api/feedback", methods=["POST"])
@login_required
@csrf.exempt
def api_feedback():
    """Сообщение пользователя администратору (об ошибке / обратная связь)."""
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Текст сообщения пуст"}), 400
    if len(text) > 2000:
        return jsonify({"error": "Сообщение слишком длинное (макс. 2000 символов)"}), 400
    db.session.add(AdminMessage(user_id=current_user.id, text=text))
    db.session.commit()
    return jsonify({"ok": True})


@chat.route("/api/password", methods=["POST"])
@login_required
@csrf.exempt
def api_password_change():
    """Смена собственного пароля (для любого вошедшего пользователя)."""
    data = request.get_json(silent=True) or {}
    current = data.get("current_password") or ""
    new = data.get("new_password") or ""
    if not current_user.check_password(current):
        return jsonify({"error": "Текущий пароль неверен"}), 400
    if len(new) < 6:
        return jsonify({"error": "Новый пароль должен быть не короче 6 символов"}), 400
    if new == current:
        return jsonify({"error": "Новый пароль совпадает с текущим"}), 400
    current_user.set_password(new)
    db.session.commit()
    return jsonify({"ok": True})


@chat.route("/api/parse", methods=["POST"])
@login_required
@csrf.exempt
def api_parse():
    data = request.get_json(silent=True) or {}
    file_path = (data.get("file_path") or "").strip()
    if not file_path:
        return jsonify({"error": "Поле 'file_path' обязательно"}), 400
    return jsonify(current_app.rag.parse_file(file_path))
