"""
Nocturna's brain, as a plain text-in / text-out function.

This replaces main.py from the voice version. The decision logic is the same
(generic utility commands first, then the course catalog, then the UTG
knowledge base), but nothing here touches a microphone or speakers, so it
works for any number of students at once through the web app.

The one real difference is follow-up questions. The voice version could just
call listen() mid-command ("Which city?"). A web request can't wait for a
second answer, so instead respond() returns a `pending` dict describing what
it is waiting for, the web layer keeps that in the student's session, and the
next message is treated as the answer. Typing "cancel" abandons it.

    reply_lines, pending = respond(user, "weather", None)
    # -> ["Which city do you want the weather for?"], {"action": "weather"}
    reply_lines, pending = respond(user, "Banjul", pending)
    # -> ["The weather in Banjul is ..."], None
"""

import re
import time
from datetime import datetime, timezone

import course_catalog as catalog
import reminders
import utilities as utils
from config import ASSISTANT_NAME
from knowledge_base import KnowledgeBase
from logger import log_interaction

kb = KnowledgeBase()

MAX_MESSAGE_CHARS = 500

_CANCEL_WORDS = {"cancel", "never mind", "nevermind", "stop", "forget it"}
_GREETINGS = {
    "hi", "hello", "hey", "hiya", "good morning", "good afternoon",
    "good evening", "salam", "assalamu alaikum", "as-salamu alaykum",
}
_THANKS = {"thanks", "thank you", "thank you so much", "thanks a lot", "many thanks"}
_GOODBYES = {"bye", "goodbye", "exit", "quit", "see you", "see you later"}

HELP_TEXT = (
    "I can answer questions about UTG admissions, schools, fees and contacts, "
    "including detailed course information for Computer Science, "
    "Telecommunication, and Information Systems: prerequisites, credit hours, "
    "electives, and semester plans (try \"prerequisite for CPS 402\").\n\n"
    "I can also tell you the time or a joke, check the weather, make a web "
    "search link, find a location, save notes (\"note: bring my ID\"), and set "
    "reminders for deadlines (\"remind me to pay fees in 3 days\").\n\n"
    "Type \"my notes\" or \"my reminders\" to see what you've saved."
)

_SEARCH_RE = re.compile(
    r"^(?:please\s+)?(?:web\s+)?(?:search|google|look\s+up)(?:\s+for)?\s*(.*)$", re.I
)
_LOCATION_RE = re.compile(r"find\s+(?:the\s+)?location(?:\s+(?:of|for))?\s*(.*)$", re.I)
_WEATHER_RE = re.compile(r"weather(?:\s+(?:in|for|at|of))?\s*(.*)$", re.I)
_NOTE_RE = re.compile(
    r"^(?:please\s+)?(?:(?:take|save|write|make|add)\s+(?:down\s+)?(?:a\s+|this\s+)?)?"
    r"note\b\s*[:,\-]?\s*(?:that\s+|to\s+)?(.*)$",
    re.I,
)
_WRITE_DOWN_RE = re.compile(r"^(?:please\s+)?write\s+down\s*[:,\-]?\s*(.+)$", re.I)
_REMIND_DESC_RE = re.compile(r"^(?:please\s+)?remind\s+me\s+(?:to\s+)?(.+)$", re.I)

_LIST_NOTES_PHRASES = ("my notes", "list notes", "show notes", "show my notes", "what notes")
_LIST_REMINDER_PHRASES = ("my reminders", "list reminders", "what reminders", "show reminders")


def _clean_arg(value: str) -> str:
    return value.strip(" \t.!?\"'")


def _first_name(user) -> str:
    return user["full_name"].split()[0]


def greeting_for(user) -> str:
    return f"Hello {_first_name(user)}, I'm {ASSISTANT_NAME}, your UTG student assistant. How can I help you today?"


def format_due_reminder(r) -> str:
    return f"Reminder: {r['description']} (due {r['due_date']})"


# ---------------------------------------------------------------- routing

def respond(user, text: str, pending=None):
    """Returns (reply_lines: list[str], new_pending: dict | None)."""
    start = time.time()
    text = " ".join(text.split())[:MAX_MESSAGE_CHARS]
    if not text:
        return [], pending

    replies, intent, source, confidence, new_pending = _route(user, text, pending)
    log_interaction(user["id"], text, intent, source, confidence, time.time() - start)
    return replies, new_pending


def _route(user, text, pending):
    lowered = text.lower()
    clean = lowered.strip(" .!?")

    if pending:
        if clean in _CANCEL_WORDS:
            return ["Okay, cancelled."], "cancel", "utility", 1.0, None
        return _continue_pending(user, text, pending)

    result = _handle_utility(user, text, lowered, clean)
    if result is not None:
        replies, intent, new_pending = result
        return replies, intent, "utility", 1.0, new_pending

    # Not a generic command -- try the UTG knowledge base.
    answer, _matched_question, confidence, source = kb.search(lowered)
    if answer:
        return [answer], "knowledge_base", source, confidence, None

    return [
        "I'm still learning. Can you try asking that another way, or "
        "type \"help\" to see what I can do?"
    ], "unmatched", "none", confidence, None


def _continue_pending(user, text, pending):
    action = pending.get("action")

    if action == "weather":
        return [utils.get_weather(_clean_arg(text))], "weather", "utility", 1.0, None
    if action == "search":
        return [utils.web_search(_clean_arg(text))], "web_search", "utility", 1.0, None
    if action == "location":
        return [utils.find_location(_clean_arg(text))], "location", "utility", 1.0, None
    if action == "note":
        return [utils.save_note(user["id"], text)], "note", "utility", 1.0, None

    if action == "remind_desc":
        new_pending = {"action": "remind_due", "description": text}
        return [_ASK_WHEN], "set_reminder", "utility", 1.0, new_pending

    if action == "remind_due":
        success, message = reminders.add_reminder(user["id"], pending["description"], text)
        # On a bad date keep waiting so the student can just retype the date.
        return [message], "set_reminder", "utility", 1.0, (None if success else pending)

    return ["Sorry, I lost track of what we were doing. Please ask again."], "error", "utility", 1.0, None


_ASK_WHEN = (
    "When should I remind you? Use a date like 2026-11-05 (year-month-day), "
    "or say 'tomorrow' or 'in 3 days'."
)


def _handle_utility(user, text, lowered, clean):
    """Returns (replies, intent, new_pending) if a utility command matched,
    otherwise None so the caller falls through to the knowledge base."""

    if clean in _GREETINGS:
        return [greeting_for(user)], "greeting", None

    if clean in _THANKS:
        return ["You're welcome! Anything else I can help with?"], "thanks", None

    if clean in _GOODBYES:
        return ["Goodbye! Come back any time."], "exit", None

    if "what is your name" in lowered or clean in ("who are you", "your name"):
        return [f"My name is {ASSISTANT_NAME}, the UTG student assistant."], "identity", None

    if "what time is it" in lowered or "what's the time" in lowered or "what is the time" in lowered:
        now = datetime.now(timezone.utc)
        # The Gambia is on GMT all year, so UTC is the correct local time there.
        return [now.strftime("It's %H:%M GMT on %A, %d %B %Y.")], "time", None

    if "joke" in lowered:
        return [utils.tell_joke()], "joke", None

    if "weather" in lowered:
        m = _WEATHER_RE.search(text)
        city = _clean_arg(m.group(1)) if m else ""
        if city:
            return [utils.get_weather(city)], "weather", None
        return ["Which city do you want the weather for?"], "weather", {"action": "weather"}

    m = _SEARCH_RE.match(text)
    if m:
        query = _clean_arg(m.group(1))
        if query:
            return [utils.web_search(query)], "web_search", None
        return ["What do you want to search for?"], "web_search", {"action": "search"}

    m = _LOCATION_RE.search(text)
    if m:
        place = _clean_arg(m.group(1))
        if place:
            return [utils.find_location(place)], "location", None
        return ["What location do you want to search for?"], "location", {"action": "location"}

    if any(p in lowered for p in _LIST_NOTES_PHRASES):
        return [utils.list_notes(user["id"])], "list_notes", None

    m = _NOTE_RE.match(text) or _WRITE_DOWN_RE.match(text)
    if m:
        content = m.group(1).strip()
        if content:
            return [utils.save_note(user["id"], content)], "note", None
        return ["What would you like me to write?"], "note", {"action": "note"}

    if any(p in lowered for p in _LIST_REMINDER_PHRASES):
        upcoming = reminders.get_upcoming_reminders(user["id"])
        if not upcoming:
            return ["You don't have any upcoming reminders."], "list_reminders", None
        lines = [f"- {r['description']} on {r['due_date']}" for r in upcoming]
        return ["Here are your upcoming reminders:\n" + "\n".join(lines)], "list_reminders", None

    if "remind me" in lowered or "set a reminder" in lowered:
        # One line with everything ("remind me to X in 3 days") works at once.
        description, due_text = reminders.parse_reminder_command(text)
        if description and due_text:
            _success, message = reminders.add_reminder(user["id"], description, due_text)
            return [message], "set_reminder", None
        # Description given but no date: only ask for the date.
        m = _REMIND_DESC_RE.match(text)
        if m and m.group(1).strip():
            return [_ASK_WHEN], "set_reminder", {"action": "remind_due", "description": m.group(1).strip()}
        return ["What should I remind you about?"], "set_reminder", {"action": "remind_desc"}

    catalog_response = catalog.handle_catalog_query(text)
    if catalog_response:
        return [catalog_response], "course_catalog", None

    if clean == "help" or "what can you do" in lowered:
        return [HELP_TEXT], "help", None

    return None
