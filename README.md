# Nocturna — UTG Student Chatbot

Nocturna started as a voice assistant. It is now a **web chatbot with
accounts**: students sign up or log in first, then chat by typing. It answers
from the same data as before (the UTG knowledge base in `utg_knowledge.json`
and the course catalog in `data/programs.json`) and keeps the same utility
commands (time, jokes, weather, search link, location link, notes,
reminders).

## What changed from the voice version

- **No microphone or speakers.** `speech_io.py`, `main.py`, `gui.py` and
  `mic_test.py` are gone, along with SpeechRecognition, gTTS, playsound and
  PyAudio (the packages that were hardest to install).
- **Accounts.** `/signup` and `/login` pages; the chat (and every `/api/*`
  route) refuses anyone who isn't logged in. Details in "Accounts and
  security" below.
- **`chatbot.py` replaces `main.py`.** Same order of checks (utility commands,
  then course catalog, then knowledge base), but it takes text and returns
  text, so many students can use it at once.
- **Follow-up questions work differently.** The voice version called
  `listen()` mid-command. Now "weather" replies "Which city…?" and your next
  message is taken as the answer. Type `cancel` to drop it. One-line forms
  still work: "weather in Banjul", "note: bring my ID", "remind me to pay
  fees in 3 days".
- **Everything personal is stored per account** in SQLite
  (`instance/nocturna.db`): chat history, notes and reminders. Notes used to
  be loose `.txt` files and reminders a shared `reminders.json`, which would
  have mixed students together.
- **Search and map commands return a clickable link** instead of opening a
  browser on the server.
- **Chat history is saved**, so a student sees their conversation again on the
  next login. "Clear chat" deletes it (notes and reminders are kept).
- Retrieval, the evaluation harness (`evaluate.py`) and the course catalog are
  unchanged, so your existing results in `eval/` are still valid.

## Setup

Requires Python 3.9 or newer.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
```

`requirements.txt` is everything the chatbot needs. `requirements-eval.txt`
adds sentence-transformers (which installs PyTorch, a large download) and
matplotlib, and is only needed for `evaluate.py` or the optional embeddings
retrieval method.

Optional environment variables:

| variable | purpose |
|---|---|
| `OPENWEATHER_API_KEY` | enables the weather command |
| `SECRET_KEY` | signs login cookies. If unset, one is generated into `instance/secret_key` (fine for local use) |
| `COOKIE_SECURE=1` | set when serving over HTTPS so cookies are never sent over plain HTTP |

## Run

```bash
python app.py
```

Open <http://127.0.0.1:5000>, click **Create an account**, then chat.

## Accounts and security

- Passwords are stored only as salted hashes (werkzeug's scrypt); minimum 8
  characters.
- Login errors don't reveal whether an email is registered. After 5 failed
  logins for the same email and IP within 10 minutes, further attempts are
  refused for a while (kept in memory, so it resets on restart).
- Every form and API call carries a CSRF token; session cookies are
  `HttpOnly` and `SameSite=Lax`; sessions last 7 days.
- Each query is filtered by `user_id`, so one student can't read another's
  chats, notes or reminders (covered by a test).
- Chat text is inserted into the page as text, never as HTML.

Before putting this on the internet: serve it with a production server
(for example `waitress` on Windows or `gunicorn` on Linux) behind HTTPS, set
`SECRET_KEY` and `COOKIE_SECURE=1`, and keep `instance/` out of version
control (the included `.gitignore` already does). Flask's built-in server is
for development.

## Tests

```bash
python -m unittest discover -s tests -v
```

20 tests cover sign-up validation, login/logout, CSRF, the open-redirect
guard, login throttling, every chat command, and isolation between two
accounts. They use a temporary database, so your real accounts are untouched.

## Project layout

```
app.py               Flask routes: chat page + JSON API
auth.py              sign up / log in / log out, CSRF, login_required
chatbot.py           the assistant's logic (text in, text out)
db.py                SQLite: users, messages, reminders, notes
config.py            settings (retrieval method, thresholds, paths, auth)
knowledge_base.py    wraps retrieval_methods.py (keyword / tfidf / embeddings)
course_catalog.py    exact lookups over data/programs.json
reminders.py         date parsing + per-user reminders
utilities.py         weather, jokes, search/map links, notes
logger.py            logs/chat_interactions.csv for evaluation
evaluate.py          compares the three retrieval methods
templates/, static/  login, sign-up and chat pages
tests/               automated tests
```

## Where the knowledge-base data came from

`utg_knowledge.json` was built from publicly available pages on
**utg.edu.gm** (Home, Schools & Faculties, the School of ICT page,
Undergraduate Admissions, and the Students Guide), accessed **1 October
2026**. Each entry is a paraphrased summary with a `source` field noting
which page it came from — the answers are rewritten for a short chat reply,
not copied text.

**Important before you rely on this for real students or for your final
submission:**
- Fees, admission requirements, and contact details on a university website
  change. Verify each fact with the relevant office (Registry, School of
  ICT, Admissions) before presenting this as authoritative — your ethics
  section already commits to getting institutional sign-off, and this is
  exactly the kind of content that needs it.
- The original pilot set was **20 entries**, deliberately scoped to the
  Schools & Faculties / ICT / Admissions area as a starting point. Expanding
  it with the academic calendar, student handbook, and examination rules
  (once you have those documents) is the natural next step, and is already
  in your proposal's Phase 1.


## Knowledge-base additions (October 2026)

26 entries were added (20 -> 46), from two kinds of source. Each entry's
`source` field says which.

1. **Photographed pages (pp. 6-11 and 14) of the "University Culture" lecture
   notes, 2014/2015.** Covers how UTG began (the University Extension
   Programme, the National Commission, the UTG Act), the Act's functions and
   guiding principles, the school list, the academic staff ranks and
   promotion requirements, lecturer and student responsibilities, exam
   cheating, MIM/STM, student unionism and the university seminar. Pages
   12-13 were not photographed, so nothing from them is included. The notes
   are from 2014/2015: the campus locations in them are marked as older, and
   the tenth school they list (Graduate Studies and Research) is not on the
   nine-school list used by the existing "schools and faculties" entry.
2. **UTG's own web pages and news reports** for the student associations
   (ECOMANSA, EDUSA, AESSA, UniGaMSA, SoSHSA/SOHSA, JSA and the full list of
   sub-associations) plus the School of Agriculture & Environment Sciences
   programme, entry requirements and fees. Facebook blocks automated access,
   so the associations' Facebook pages themselves could not be read; the
   Agriculture and Environmental Sciences association's page appeared in
   search results but only as a short snippet.

Things to double-check before relying on them: the Agriculture tuition figures
(fees change each year), and the association name spellings (the handbook
writes SOHSA, the students' union site writes SoSHSA, news reports write
SHoSHA).

### Effect on retrieval accuracy

TF-IDF scores depend on every question in the knowledge base, so adding
entries shifted them. On the original 70-query test set:

| setup | tfidf correct |
|---|---|
| original 20-entry KB, original method | 57/70 (81.4%) |
| 46-entry KB, original method | 51/70 (72.9%) |
| 46-entry KB, `"utg"` ignored (now the default) | 56/70 (80.0%) |

The drop came from out-of-scope questions such as "is there a football team
at utg" scoring highly just because they contain "utg", a word in nearly
every question. `TFIDF_EXTRA_STOPWORDS = ("utg",)` in `config.py` ignores it;
set it to `()` to reproduce the original method. `eval/test_set_v2.json` is
the original 70 queries plus 54 for the new entries (124 total); on it tfidf
scores 108/124 (87.1%) with "utg" ignored. `evaluate.py` still reads
`eval/test_set.json`, so your earlier results are unchanged; change
`TEST_SET_PATH` to use the v2 file.

## How to use the logs for your evaluation chapter

Every query appends a row to `logs/chat_interactions.csv`:

| column | meaning |
|---|---|
| `user_id` | numeric id of the account that sent it (no name or email) |
| `query` | what the student typed |
| `intent` | `utility` command name, `knowledge_base`, or `unmatched` |
| `source` | which KB entry answered it (or blank) |
| `confidence` | similarity score (0–1) |
| `response_time_s` | time from query to reply |

Load this into pandas or Excel after a test session to compute intent
accuracy, hit rate, and latency distributions directly.

## Course catalog: prerequisites, credit hours, electives, semester plans

Beyond the general FAQ knowledge base, the assistant now has a **structured
course catalog** (`course_catalog.py` + `data/programs.json`) covering all
three SITC departments -- Computer Science, Telecommunication, and
Information Systems (full 4-year study plans, 47-133 courses each,
electives, and programme-level credit-hour requirements).

This is deliberately a *different* system from the FAQ retrieval methods
(`retrieval_methods.py`): "what is the prerequisite for CPS 402" needs an
exact structured answer, not a similarity match against a bank of Q&A
pairs, so it's answered by direct lookup instead. Try asking (typed):

- "What is the prerequisite for CPS 402?"
- "How many credit hours is ICT 210?"
- "What are the major requirements for computer science?"
- "What are the information systems electives?"
- "What courses are in year 3 semester 1 for information systems?"
- "Tell me about INS 403."

### Where the data came from, and what was deliberately left out

- `BSc_Computer_Science.docx` and `BSc_Telecom_2022.docx` (semester-by-
  semester study plans) and the Information Systems study plan PDF are the
  full source for `data/programs.json`. `data/build_catalog.py` is the
  transcription script, kept for auditability -- every semester's credit
  total is checked by assertion against the "Total" row printed in its own
  source document (and the Information Systems section additionally checks
  against that PDF's own printed "148 credits, 47 courses" summary). All
  checks passed.
- Two photographed "Major/Minor Requirements" sheets were **not** used for
  their detailed course-code tables. The student confirmed those photos are
  from a different catalog year than the docx/PDF study plans, and their
  tables used different course codes and credit hours for what should be
  the same courses (e.g. "ICT 205 Data Structure & Algorithms" in the photo
  vs. "ICT 210 Data Structure & Algorithms" in the docx) -- merging them
  would have risked giving students a wrong course code. Only the short
  overview paragraphs at the top of those photos (total credit hours
  required, GER/DER/core/elective structure) were kept, as
  `major_requirements_overview` / `minor_overview` text in
  `data/programs.json` -- those don't name specific course codes, so they
  don't carry the same risk.
- A Computer Science **minor** exists (confirmed by that overview text) but
  has no structured course-by-course lookup here, for the same reason --
  the only source for its specific course list was the unreliable
  photographed table.

### Extending this later

Once you have the current, verified Computer Science minor course list
(or if the department confirms the docx study plans are themselves
outdated), add it the same way: extend `data/build_catalog.py` following
the existing pattern, with an assertion checking your transcription against
the source's own printed totals, then re-run it to regenerate
`data/programs.json`.

## Why this isn't redundant with email/WhatsApp

UTG already pushes academic updates to students by email and WhatsApp
group, so "the assistant tells you things" isn't by itself a reason to use
it. The actual differentiation is structural, not cosmetic:

1. **Pull vs. push.** Email and WhatsApp are broadcast channels — one
   message, sent once, to everyone, in chronological order. Finding "what
   did the registrar say about deferment three weeks ago" means scrolling.
   This assistant is a standing index: the same fact, answerable instantly,
   whenever you ask, for as long as it's in the knowledge base.

2. **Personal, proactive reminders** (`reminders.py`, new this round) — the
   one thing a group broadcast genuinely cannot do. A WhatsApp group can
   tell 300 students "registration closes Friday." It can't tell *you*,
   specifically, three weeks later, that you still haven't registered and
   it's due tomorrow. `remind me to <thing> in <N> days` does exactly that,
   and the assistant checks and announces due reminders on startup.

3. **One interface instead of three.** Right now a student's academic life
   is split across email, a WhatsApp group, and the registrar's office.
   Once populated with real handbook/calendar content, this assistant
   becomes a single place to ask, regardless of which channel the original
   information came from.

4. **Accessible hands-free**, which matters concretely for late-night
   studying (the whole reason for the Nocturna framing) and for anyone who
   finds navigating text-heavy admin pages inconvenient.

What this does **not** claim: it isn't trying to replace official
communication, and it isn't claiming to have better or more current
information than the Registry — it's a faster way to retrieve and be
reminded of things that are otherwise scattered and easy to lose track of.
That's the honest version of the pitch, and it's the one worth defending.

### Extending with real procedural content

I looked for UTG's own published transcript/deferment/add-drop procedures
to add to the knowledge base and found nothing on the public website —
every result was from a different university entirely. That content almost
certainly exists only in a printed or internal student handbook. Rather
than invent steps, fees, or deadlines for something students could get
real consequences from getting wrong, `utg_knowledge.json` is ready for you
to add real entries once you have that handbook (see your proposal's Phase
1). The format is simple — just append objects shaped like:

```json
{
  "question": "how do i apply for deferment",
  "answer": "<the real, verified procedure, written for a short chat reply>",
  "source": "UTG Student Handbook, obtained from Registry, <date>"
}
```

That's the single highest-value content addition left for this project,
and it's a content task, not an engineering one — the retrieval system
already handles it.

## Comparing retrieval methods (the evaluation that makes this a thesis, not a demo)

The assistant now has **three interchangeable retrieval methods**
(`retrieval_methods.py`), all sharing one interface so they can be
benchmarked against each other on the same labelled test set:

| Method | What it does | Needs internet? |
|---|---|---|
| `keyword` | Token-overlap scoring — a fair, generalised version of the *original* prototype's `"x" in voice_data` approach. This is your baseline. | No |
| `tfidf` | TF-IDF + cosine similarity. What the assistant used right before this upgrade. | No |
| `embeddings` | Pretrained sentence-embedding similarity (`all-MiniLM-L6-v2`), matches on *meaning* rather than shared words. | Yes, first run only (downloads ~90MB, then cached) |

### Running the evaluation

```bash
python evaluate.py
```

This runs all three methods against `eval/test_set.json` — 70 labelled
queries across four categories (direct, paraphrased, noisy/spoken-style,
and out-of-scope) — and produces:

- `eval/results.csv` — every (method, query) pair, with what it matched,
  its confidence score, and whether it was correct. **This is your
  error-analysis data** — filter to `correct == False` for one method to
  see exactly what it gets wrong and why.
- `eval/summary.csv` — one row per method: overall accuracy, per-category
  accuracy, and average latency.
- `eval/comparison_chart.png` — bar chart of overall accuracy, ready to
  drop into your results chapter.

I ran `keyword` and `tfidf` already (my dev environment's network doesn't
reach Hugging Face, so I couldn't download the embedding model here) —
real results, not estimates:

| Method | Overall | Direct | Paraphrase | Noisy | Out-of-scope |
|---|---|---|---|---|---|
| keyword | 78.6% | 100% | 60% | 80% | 75% |
| tfidf | 81.4% | 100% | 70% | 90% | 70% |
| embeddings | *run it yourself* | | | | |

Notice TF-IDF doesn't win on *everything* — it's better at paraphrase and
noisy queries but slightly worse on out-of-scope rejection (more false
positives on queries that happen to share words like "utg"). That
trade-off, not just a single accuracy number, is the actual finding worth
discussing. Run `python evaluate.py` yourself to get the real embeddings
numbers, then decide — don't assume embeddings "should" win; report what
the data shows.

### Using the result

Once you know which method performs best, set it as the live assistant's
default in `config.py`:

```python
RETRIEVAL_METHOD = "embeddings"   # or "tfidf" / "keyword"
```

`chatbot.py` and `app.py` both pick this up automatically through
`knowledge_base.py` — nothing else needs to change.

### Extending the test set

70 queries is a reasonable starting evaluation set for a tight timeline,
but it's hand-authored by me as a starting point, not independently
validated — `eval/test_set.json` is a plain JSON list, so adding more
queries (ideally ones real students actually ask, once you have pilot
users) is just appending more
`{"query": ..., "expected_question": ..., "category": ...}` objects.
`expected_question` must exactly match a `question` field in
`utg_knowledge.json`, or be `null` for an out-of-scope query.

## Known limitations

- Reminders are only shown when the student opens the chat; there is no
  email, SMS or push notification yet.
- Matching of commands like "weather" or "joke" is still keyword-based, as in
  the original prototype. Anything UTG-specific goes through retrieval.
- There is no password reset or email verification yet (both need an email
  service). Anyone can sign up with any email address.
- The login throttle is in memory and per process.
- English only. The Wolof speech plan from the voice version no longer
  applies directly; a typed chatbot could instead take Wolof text input.

## Suggested next steps

1. Expand `utg_knowledge.json` with academic calendar and handbook content
   (the data sections above explain how to verify and add entries).
2. Add password reset by email, and optionally restrict sign-up to
   `@utg.edu.gm` addresses if you want UTG students only.
3. Add a "delete my account" option that removes the user and, through the
   database's cascade rules, all of their messages, notes and reminders.
4. Add an admin view of `logs/chat_interactions.csv` to spot unanswered
   questions and grow the knowledge base from them.
