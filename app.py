"""
Web app for Nocturna: a login-protected chatbot for UTG students.

Run with:
    python app.py
Then open http://127.0.0.1:5000 in your browser. You'll be sent to the login
page; create an account on the sign-up page the first time.

Layout:
    auth.py      sign up / log in / log out, CSRF protection, login_required
    chatbot.py   the assistant's logic (text in, text out)
    db.py        SQLite storage (accounts, chat history, reminders, notes)

Nothing here needs a microphone or speakers any more, so the server can
handle several students at the same time.
"""

from datetime import timedelta

from flask import Flask, g, jsonify, render_template, request, session

import auth
import chatbot
import db
import reminders
from config import COOKIE_SECURE, SECRET_KEY, SESSION_DAYS

app = Flask(__name__)
app.config.update(
    SECRET_KEY=SECRET_KEY,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=COOKIE_SECURE,
    PERMANENT_SESSION_LIFETIME=timedelta(days=SESSION_DAYS),
    MAX_CONTENT_LENGTH=16 * 1024,  # chat messages are tiny; refuse anything big
)

db.init_db()
auth.init_app(app)  # CSRF, current-user loader, and the /login /signup /logout routes


@app.after_request
def _security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/")
@auth.login_required
def index():
    return render_template("chat.html", user=g.user)


@app.route("/api/history")
@auth.login_required
def api_history():
    """Returns the student's saved conversation. A brand-new account gets the
    greeting stored as its first message so it's part of the history too."""
    messages = db.get_messages(g.user["id"])
    if not messages:
        greeting = chatbot.greeting_for(g.user)
        db.add_message(g.user["id"], "bot", greeting)
        messages = db.get_messages(g.user["id"])
    return jsonify(messages=messages)


@app.route("/api/due_reminders")
@auth.login_required
def api_due_reminders():
    """Called when the chat page opens: surfaces reminders due today or
    overdue, once each, and saves them into the conversation."""
    lines = []
    for r in reminders.get_due_reminders(g.user["id"]):
        text = chatbot.format_due_reminder(r)
        db.add_message(g.user["id"], "bot", text)
        lines.append(text)
    return jsonify(due=lines)


@app.route("/api/chat", methods=["POST"])
@auth.login_required
def api_chat():
    payload = request.get_json(silent=True) or {}
    text = " ".join(str(payload.get("text") or "").split())
    if not text:
        return jsonify(error="Please type a message."), 400
    if len(text) > chatbot.MAX_MESSAGE_CHARS:
        return jsonify(error=f"Please keep messages under {chatbot.MAX_MESSAGE_CHARS} characters."), 400

    user_id = g.user["id"]
    db.add_message(user_id, "user", text)

    replies, pending = chatbot.respond(g.user, text, session.get("pending"))
    if pending:
        session["pending"] = pending
    else:
        session.pop("pending", None)

    for line in replies:
        db.add_message(user_id, "bot", line)
    return jsonify(replies=replies)


@app.route("/api/clear", methods=["POST"])
@auth.login_required
def api_clear():
    db.clear_messages(g.user["id"])
    session.pop("pending", None)
    return jsonify(ok=True)


@app.errorhandler(400)
def _bad_request(err):
    return render_template("error.html", message=getattr(err, "description", "Bad request.")), 400


@app.errorhandler(413)
def _too_large(err):
    return jsonify(error="That message is too large."), 413


if __name__ == "__main__":
    # debug stays off on purpose: Flask's debugger lets anyone who can reach
    # the page run code on your machine.
    app.run(host="127.0.0.1", port=5000, debug=False)
