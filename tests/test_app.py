"""
End-to-end tests for the login system and the chat API.

Run from the project folder with:
    python -m unittest discover -s tests -v

Each run uses a throwaway database and log file in a temp folder, so your
real accounts in instance/nocturna.db are never touched.
"""

import os
import re
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# pyjokes is only used for the joke command; stub it if it isn't installed so
# the rest of the suite can still run.
try:
    import pyjokes  # noqa: F401
except ModuleNotFoundError:
    stub = types.ModuleType("pyjokes")
    stub.get_joke = lambda: "A test joke."
    sys.modules["pyjokes"] = stub

import config  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="nocturna_test_")
config.DB_PATH = os.path.join(_TMP, "test.db")
config.LOG_PATH = os.path.join(_TMP, "log.csv")

import app as app_module  # noqa: E402
import db  # noqa: E402
import logger  # noqa: E402

logger.LOG_PATH = config.LOG_PATH
db.DB_PATH = config.DB_PATH
db.init_db()

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
META_RE = re.compile(r'name="csrf-token" content="([^"]+)"')


class Client:
    """A browser-like wrapper: keeps cookies and handles CSRF tokens."""

    def __init__(self):
        self.c = app_module.app.test_client()

    def form_token(self, path):
        html = self.c.get(path).get_data(as_text=True)
        return CSRF_RE.search(html).group(1)

    def signup(self, name="Awa Jallow", email="awa@example.com", pw="correct horse", confirm=None):
        token = self.form_token("/signup")
        return self.c.post("/signup", data={
            "csrf_token": token, "full_name": name, "email": email,
            "password": pw, "confirm": pw if confirm is None else confirm,
        })

    def login(self, email="awa@example.com", pw="correct horse", next_url=None):
        token = self.form_token("/login")
        data = {"csrf_token": token, "email": email, "password": pw}
        if next_url:
            data["next"] = next_url
        return self.c.post("/login", data=data)

    def api_token(self):
        html = self.c.get("/").get_data(as_text=True)
        return META_RE.search(html).group(1)

    def chat(self, text):
        r = self.c.post("/api/chat", json={"text": text}, headers={"X-CSRF-Token": self.api_token()})
        return r.status_code, r.get_json()


class AuthTests(unittest.TestCase):
    def test_protected_pages_require_login(self):
        c = Client()
        r = c.c.get("/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])
        self.assertEqual(c.c.get("/api/history").status_code, 401)
        r = c.c.post("/api/chat", json={"text": "hi"})
        self.assertIn(r.status_code, (400, 401))

    def test_signup_requires_csrf(self):
        c = Client()
        r = c.c.post("/signup", data={"full_name": "X Y", "email": "x@y.com", "password": "password1", "confirm": "password1"})
        self.assertEqual(r.status_code, 400)

    def test_signup_validation(self):
        c = Client()
        r = c.signup(email="not-an-email")
        self.assertEqual(r.status_code, 400)
        self.assertIn("valid email", r.get_data(as_text=True))
        r = c.signup(email="v1@example.com", pw="short")
        self.assertIn("at least 8", r.get_data(as_text=True))
        r = c.signup(email="v2@example.com", pw="longenough1", confirm="different1")
        self.assertIn("don&#39;t match", r.get_data(as_text=True))
        r = c.signup(name="A", email="v3@example.com")
        self.assertIn("full name", r.get_data(as_text=True))

    def test_signup_login_logout_cycle(self):
        c = Client()
        r = c.signup(name="Lamin Ceesay", email="lamin@example.com")
        self.assertEqual(r.status_code, 302)
        page = c.c.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Lamin Ceesay", page.get_data(as_text=True))

        # password is stored hashed, never as typed
        stored = db.get_user_by_email("lamin@example.com")["password_hash"]
        self.assertNotIn("correct horse", stored)

        token = c.api_token()
        r = c.c.post("/logout", data={"csrf_token": token})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(c.c.get("/").status_code, 302)

        r = c.login("lamin@example.com", "wrong password")
        self.assertEqual(r.status_code, 401)
        self.assertIn("Incorrect email or password", r.get_data(as_text=True))
        r = c.login("lamin@example.com")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(c.c.get("/").status_code, 200)

    def test_duplicate_email_case_insensitive(self):
        Client().signup(email="dup@example.com")
        r = Client().signup(email="DUP@Example.com")
        self.assertEqual(r.status_code, 400)
        self.assertIn("already exists", r.get_data(as_text=True))

    def test_unknown_email_gives_same_message(self):
        r = Client().login("nobody@example.com", "whatever123")
        self.assertEqual(r.status_code, 401)
        self.assertIn("Incorrect email or password", r.get_data(as_text=True))

    def test_open_redirect_blocked(self):
        Client().signup(email="redir@example.com")
        c = Client()
        r = c.login("redir@example.com", next_url="//evil.example")
        self.assertEqual(r.status_code, 302)
        self.assertNotIn("evil", r.headers["Location"])

    def test_login_throttle(self):
        Client().signup(email="throttle@example.com")
        c = Client()
        for _ in range(5):
            c.login("throttle@example.com", "badbadbad1")
        r = c.login("throttle@example.com", "correct horse")  # right password, still locked
        self.assertEqual(r.status_code, 401)
        self.assertIn("Too many failed attempts", r.get_data(as_text=True))


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.c = Client()
        email = f"chat{id(self)}@example.com"
        self.c.signup(name="Fatou Sanneh", email=email)
        self.email = email

    def test_history_starts_with_personal_greeting(self):
        r = self.c.c.get("/api/history").get_json()
        self.assertEqual(len(r["messages"]), 1)
        self.assertIn("Hello Fatou", r["messages"][0]["content"])

    def test_csrf_header_required_for_chat(self):
        r = self.c.c.post("/api/chat", json={"text": "help"})
        self.assertEqual(r.status_code, 400)

    def test_knowledge_base_and_catalog_answers(self):
        _, data = self.c.chat("what schools and faculties does utg have")
        self.assertIn("nine schools", data["replies"][0])
        _, data = self.c.chat("what is the prerequisite for CPS 402")
        self.assertIn("prerequisite", data["replies"][0].lower())

    def test_unmatched_and_empty(self):
        _, data = self.c.chat("zxqv blorf wibble")
        self.assertIn("still learning", data["replies"][0])
        status, _ = self.c.chat("   ")
        self.assertEqual(status, 400)
        status, _ = self.c.chat("x" * 600)
        self.assertEqual(status, 400)

    def test_greeting_help_and_time(self):
        _, data = self.c.chat("hello")
        self.assertIn("Fatou", data["replies"][0])
        _, data = self.c.chat("help")
        self.assertIn("admissions", data["replies"][0])
        _, data = self.c.chat("what time is it")
        self.assertIn("GMT", data["replies"][0])

    def test_weather_follow_up_and_cancel(self):
        _, data = self.c.chat("weather")
        self.assertIn("Which city", data["replies"][0])
        _, data = self.c.chat("cancel")
        self.assertEqual(data["replies"][0], "Okay, cancelled.")
        # after cancelling, a normal question is answered normally again
        _, data = self.c.chat("what schools and faculties does utg have")
        self.assertIn("nine schools", data["replies"][0])

    def test_search_returns_link(self):
        _, data = self.c.chat("search for utg admissions")
        self.assertIn("https://www.google.com/search?q=utg%20admissions", data["replies"][0])

    def test_notes(self):
        _, data = self.c.chat("note: Bring my ID to registration")
        self.assertIn("saved", data["replies"][0])
        _, data = self.c.chat("take a note")
        self.assertIn("What would you like", data["replies"][0])
        _, data = self.c.chat("Buy a calculator")
        self.assertIn("saved", data["replies"][0])
        _, data = self.c.chat("my notes")
        self.assertIn("Bring my ID to registration", data["replies"][0])  # case kept
        self.assertIn("Buy a calculator", data["replies"][0])

    def test_reminders_one_line_and_step_by_step(self):
        _, data = self.c.chat("remind me to pay fees in 3 days")
        self.assertIn("pay fees", data["replies"][0])
        _, data = self.c.chat("remind me to submit my assignment")
        self.assertIn("When should I remind you", data["replies"][0])
        _, data = self.c.chat("sometime soon")
        self.assertIn("couldn't understand that date", data["replies"][0])
        _, data = self.c.chat("tomorrow")
        self.assertIn("submit my assignment", data["replies"][0])
        _, data = self.c.chat("my reminders")
        self.assertIn("pay fees", data["replies"][0])
        self.assertIn("submit my assignment", data["replies"][0])

    def test_due_reminder_shown_once(self):
        self.c.chat("remind me to renew my ID today")
        first = self.c.c.get("/api/due_reminders").get_json()["due"]
        self.assertEqual(len(first), 1)
        self.assertIn("renew my ID", first[0])
        second = self.c.c.get("/api/due_reminders").get_json()["due"]
        self.assertEqual(second, [])

    def test_clear_chat_keeps_notes(self):
        self.c.chat("note: keep me")
        r = self.c.c.post("/api/clear", json={}, headers={"X-CSRF-Token": self.c.api_token()})
        self.assertEqual(r.status_code, 200)
        msgs = self.c.c.get("/api/history").get_json()["messages"]
        self.assertEqual(len(msgs), 1)  # fresh greeting only
        _, data = self.c.chat("my notes")
        self.assertIn("keep me", data["replies"][0])

    def test_users_cannot_see_each_others_data(self):
        self.c.chat("note: private to fatou")
        self.c.chat("remind me to do secret thing tomorrow")
        other = Client()
        other.signup(name="Omar Bah", email=f"other{id(self)}@example.com")
        _, data = other.chat("my notes")
        self.assertNotIn("private to fatou", data["replies"][0])
        _, data = other.chat("my reminders")
        self.assertNotIn("secret thing", data["replies"][0])
        history = " ".join(m["content"] for m in other.c.get("/api/history").get_json()["messages"])
        self.assertNotIn("private to fatou", history)


if __name__ == "__main__":
    unittest.main()
