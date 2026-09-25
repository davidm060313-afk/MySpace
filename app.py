from flask import Flask, render_template, request, redirect, session, jsonify
import os
from dotenv import load_dotenv

load_dotenv()


import sqlite3
import psycopg2
import requests
import time
import traceback

from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from google import genai


app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "myspace-local-secret-change-this"
)

DATABASE_URL = os.environ.get("DATABASE_URL")


# ============================================================
# MYAI CONFIGURATION
# ============================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
print("MyAI Render API key loaded:", bool(GEMINI_API_KEY))

SEARXNG_URL = os.environ.get(
    "SEARXNG_URL",
    "http://localhost:8080"
)

if GEMINI_API_KEY:
    gemini_client = genai.Client(
        api_key=GEMINI_API_KEY
    )
else:
    gemini_client = None


# Gemini models
AI_MODELS = [
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.7-flash",
    "gemini-3.8-flash"
]

# ============================================================
# MYAI SAFETY FILTER
# ============================================================

BLOCKED_PATTERNS = [
    "steal a password",
    "steal passwords",
    "hack someone's account",
    "hack someones account",
    "bypass a password",
    "make malware",
    "create malware",
    "write ransomware",
    "make ransomware",
    "steal credit card",
    "steal someone's money",
    "steal someones money"
]


def safety_check(message):

    text = message.lower()

    for pattern in BLOCKED_PATTERNS:

        if pattern in text:
            return False

    return True


# ============================================================
# DATABASE
# ============================================================

def get_db():

    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)

    conn = sqlite3.connect("myspace.db")
    conn.row_factory = sqlite3.Row

    return conn


def is_postgres():

    return bool(DATABASE_URL)


def setup_database():

    conn = get_db()
    cursor = conn.cursor()

    if is_postgres():

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pages (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                icon TEXT NOT NULL DEFAULT '📄',
                favorite INTEGER NOT NULL DEFAULT 0,
                folder_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS folders (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL
            )
        """)

    else:

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                icon TEXT NOT NULL DEFAULT '📄',
                favorite INTEGER NOT NULL DEFAULT 0,
                folder_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL
            )
        """)

        columns = cursor.execute(
            "PRAGMA table_info(pages)"
        ).fetchall()

        column_names = [column[1] for column in columns]

        if "icon" not in column_names:

            cursor.execute("""
                ALTER TABLE pages
                ADD COLUMN icon TEXT NOT NULL DEFAULT '📄'
            """)

        if "favorite" not in column_names:

            cursor.execute("""
                ALTER TABLE pages
                ADD COLUMN favorite INTEGER NOT NULL DEFAULT 0
            """)

        if "folder_id" not in column_names:

            cursor.execute("""
                ALTER TABLE pages
                ADD COLUMN folder_id INTEGER
            """)

    conn.commit()
    conn.close()

    return "OK"


# ============================================================
# INITIALIZE DATABASE
# ============================================================

setup_database()


# ============================================================
# LOGIN REQUIRED
# ============================================================

def login_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if "user_id" not in session:
            return redirect("/login")

        return function(*args, **kwargs)

    return wrapper


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    if "user_id" not in session:
        return redirect("/login")

    return redirect("/workspace")


# ============================================================
# REGISTER
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        if len(username) < 3:

            return render_template(
                "register.html",
                error="Username must be at least 3 characters."
            )

        if len(password) < 4:

            return render_template(
                "register.html",
                error="Password must be at least 4 characters."
            )

        password_hash = generate_password_hash(password)

        conn = get_db()
        cursor = conn.cursor()

        try:

            if is_postgres():

                cursor.execute(
                    """
                    INSERT INTO users
                    (username, password)
                    VALUES (%s, %s)
                    RETURNING id
                    """,
                    (
                        username,
                        password_hash
                    )
                )

                user_id = cursor.fetchone()[0]

            else:

                cursor.execute(
                    """
                    INSERT INTO users
                    (username, password)
                    VALUES (?, ?)
                    """,
                    (
                        username,
                        password_hash
                    )
                )

                user_id = cursor.lastrowid

            conn.commit()

        except Exception:

            conn.rollback()
            conn.close()

            return render_template(
                "register.html",
                error="That username already exists."
            )

        conn.close()

        session.clear()

        session["user_id"] = user_id
        session["username"] = username

        return redirect("/workspace")

    return render_template("register.html")


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        conn = get_db()
        cursor = conn.cursor()

        if is_postgres():

            cursor.execute(
                """
                SELECT id, username, password
                FROM users
                WHERE username = %s
                """,
                (username,)
            )

        else:

            cursor.execute(
                """
                SELECT id, username, password
                FROM users
                WHERE username = ?
                """,
                (username,)
            )

        user = cursor.fetchone()

        conn.close()

        if user:

            user_id = user[0]
            saved_username = user[1]
            saved_password = user[2]

            if check_password_hash(
                saved_password,
                password
            ):

                session.clear()

                session["user_id"] = user_id
                session["username"] = saved_username

                return redirect("/workspace")

        return render_template(
            "login.html",
            error="Incorrect username or password."
        )

    return render_template("login.html")


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")


# ============================================================
# WORKSPACE
# ============================================================

@app.route("/workspace")
@login_required
def workspace():

    conn = get_db()
    cursor = conn.cursor()

    if is_postgres():

        cursor.execute(
            """
            SELECT
                id,
                user_id,
                title,
                content,
                icon,
                favorite,
                folder_id,
                created_at,
                updated_at
            FROM pages
            WHERE user_id = %s
            ORDER BY favorite DESC, updated_at DESC
            """,
            (session["user_id"],)
        )

        pages_raw = cursor.fetchall()

        cursor.execute(
            """
            SELECT id, user_id, name
            FROM folders
            WHERE user_id = %s
            ORDER BY name
            """,
            (session["user_id"],)
        )

        folders_raw = cursor.fetchall()

        pages = [
            {
                "id": r[0],
                "user_id": r[1],
                "title": r[2],
                "content": r[3],
                "icon": r[4],
                "favorite": r[5],
                "folder_id": r[6],
                "created_at": r[7],
                "updated_at": r[8]
            }
            for r in pages_raw
        ]

        folders = [
            {
                "id": r[0],
                "user_id": r[1],
                "name": r[2]
            }
            for r in folders_raw
        ]

    else:

        pages = cursor.execute(
            """
            SELECT *
            FROM pages
            WHERE user_id = ?
            ORDER BY favorite DESC, updated_at DESC
            """,
            (session["user_id"],)
        ).fetchall()

        folders = cursor.execute(
            """
            SELECT *
            FROM folders
            WHERE user_id = ?
            ORDER BY name
            """,
            (session["user_id"],)
        ).fetchall()

    conn.close()

    return render_template(
        "index.html",
        pages=pages,
        folders=folders,
        selected=None
    )


# ============================================================
# OPEN PAGE
# ============================================================

@app.route("/page/<int:page_id>")
@login_required
def page(page_id):

    conn = get_db()
    cursor = conn.cursor()

    if is_postgres():

        cursor.execute(
            """
            SELECT
                id,
                user_id,
                title,
                content,
                icon,
                favorite,
                folder_id,
                created_at,
                updated_at
            FROM pages
            WHERE id = %s
            AND user_id = %s
            """,
            (
                page_id,
                session["user_id"]
            )
        )

        r = cursor.fetchone()

        if r:

            selected = {
                "id": r[0],
                "user_id": r[1],
                "title": r[2],
                "content": r[3],
                "icon": r[4],
                "favorite": r[5],
                "folder_id": r[6],
                "created_at": r[7],
                "updated_at": r[8]
            }

        else:
            selected = None

        cursor.execute(
            """
            SELECT *
            FROM pages
            WHERE user_id = %s
            ORDER BY favorite DESC, updated_at DESC
            """,
            (session["user_id"],)
        )

        rows = cursor.fetchall()

        pages = [
            {
                "id": r[0],
                "user_id": r[1],
                "title": r[2],
                "content": r[3],
                "icon": r[4],
                "favorite": r[5],
                "folder_id": r[6],
                "created_at": r[7],
                "updated_at": r[8]
            }
            for r in rows
        ]

        cursor.execute(
            """
            SELECT *
            FROM folders
            WHERE user_id = %s
            ORDER BY name
            """,
            (session["user_id"],)
        )

        rows = cursor.fetchall()

        folders = [
            {
                "id": r[0],
                "user_id": r[1],
                "name": r[2]
            }
            for r in rows
        ]

    else:

        selected = cursor.execute(
            """
            SELECT *
            FROM pages
            WHERE id = ?
            AND user_id = ?
            """,
            (
                page_id,
                session["user_id"]
            )
        ).fetchone()

        pages = cursor.execute(
            """
            SELECT *
            FROM pages
            WHERE user_id = ?
            ORDER BY favorite DESC, updated_at DESC
            """,
            (session["user_id"],)
        ).fetchall()

        folders = cursor.execute(
            """
            SELECT *
            FROM folders
            WHERE user_id = ?
            ORDER BY name
            """,
            (session["user_id"],)
        ).fetchall()

    conn.close()

    if selected is None:
        return redirect("/workspace")

    return render_template(
        "index.html",
        pages=pages,
        folders=folders,
        selected=selected
    )


# ============================================================
# NEW PAGE
# ============================================================

@app.route("/new", methods=["POST"])
@login_required
def new_page():

    conn = get_db()
    cursor = conn.cursor()

    if is_postgres():

        cursor.execute(
            """
            INSERT INTO pages
            (user_id, title, content, icon)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (
                session["user_id"],
                "Untitled",
                "",
                "📄"
            )
        )

        page_id = cursor.fetchone()[0]

    else:

        cursor.execute(
            """
            INSERT INTO pages
            (user_id, title, content, icon)
            VALUES (?, ?, ?, ?)
            """,
            (
                session["user_id"],
                "Untitled",
                "",
                "📄"
            )
        )

        page_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return redirect(f"/page/{page_id}")


# ============================================================
# SAVE PAGE
# ============================================================

@app.route("/save/<int:page_id>", methods=["POST"])
@login_required
def save(page_id):

    title = request.form.get(
        "title",
        ""
    ).strip()

    content = request.form.get(
        "content",
        ""
    )

    icon = request.form.get(
        "icon",
        "📄"
    ).strip()

    if not title:
        title = "Untitled"

    if not icon:
        icon = "📄"

    conn = get_db()
    cursor = conn.cursor()

    if is_postgres():

        cursor.execute(
            """
            UPDATE pages
            SET title = %s,
                content = %s,
                icon = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            AND user_id = %s
            """,
            (
                title,
                content,
                icon,
                page_id,
                session["user_id"]
            )
        )

    else:

        cursor.execute(
            """
            UPDATE pages
            SET title = ?,
                content = ?,
                icon = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            AND user_id = ?
            """,
            (
                title,
                content,
                icon,
                page_id,
                session["user_id"]
            )
        )

    conn.commit()
    conn.close()

    return "OK"


# ============================================================
# DELETE
# ============================================================

@app.route("/delete/<int:page_id>", methods=["POST"])
@login_required
def delete(page_id):

    conn = get_db()
    cursor = conn.cursor()

    if is_postgres():

        cursor.execute(
            """
            DELETE FROM pages
            WHERE id = %s
            AND user_id = %s
            """,
            (
                page_id,
                session["user_id"]
            )
        )

    else:

        cursor.execute(
            """
            DELETE FROM pages
            WHERE id = ?
            AND user_id = ?
            """,
            (
                page_id,
                session["user_id"]
            )
        )

    conn.commit()
    conn.close()

    return "OK"


# ============================================================
# FAVORITE
# ============================================================

@app.route("/favorite/<int:page_id>", methods=["POST"])
@login_required
def favorite(page_id):

    conn = get_db()
    cursor = conn.cursor()

    if is_postgres():

        cursor.execute(
            """
            SELECT favorite
            FROM pages
            WHERE id = %s
            AND user_id = %s
            """,
            (
                page_id,
                session["user_id"]
            )
        )

    else:

        cursor.execute(
            """
            SELECT favorite
            FROM pages
            WHERE id = ?
            AND user_id = ?
            """,
            (
                page_id,
                session["user_id"]
            )
        )

    row = cursor.fetchone()

    if row:

        new_value = 0 if row[0] else 1

        if is_postgres():

            cursor.execute(
                """
                UPDATE pages
                SET favorite = %s
                WHERE id = %s
                AND user_id = %s
                """,
                (
                    new_value,
                    page_id,
                    session["user_id"]
                )
            )

        else:

            cursor.execute(
                """
                UPDATE pages
                SET favorite = ?
                WHERE id = ?
                AND user_id = ?
                """,
                (
                    new_value,
                    page_id,
                    session["user_id"]
                )
            )

    conn.commit()
    conn.close()

    return "OK"


# ============================================================
# CREATE FOLDER
# ============================================================

@app.route("/folder/new", methods=["POST"])
@login_required
def create_folder():

    name = request.form.get(
        "name",
        ""
    ).strip()

    if name:

        conn = get_db()
        cursor = conn.cursor()

        if is_postgres():

            cursor.execute(
                """
                INSERT INTO folders
                (user_id, name)
                VALUES (%s, %s)
                """,
                (
                    session["user_id"],
                    name
                )
            )

        else:

            cursor.execute(
                """
                INSERT INTO folders
                (user_id, name)
                VALUES (?, ?)
                """,
                (
                    session["user_id"],
                    name
                )
            )

        conn.commit()
        conn.close()

    return redirect("/workspace")


# ============================================================
# MOVE PAGE
# ============================================================

@app.route("/move/<int:page_id>", methods=["POST"])
@login_required
def move_page(page_id):

    folder_id = request.form.get(
        "folder_id"
    )

    if folder_id == "":
        folder_id = None

    conn = get_db()
    cursor = conn.cursor()

    if is_postgres():

        if folder_id is not None:

            cursor.execute(
                """
                SELECT id
                FROM folders
                WHERE id = %s
                AND user_id = %s
                """,
                (
                    folder_id,
                    session["user_id"]
                )
            )

            if cursor.fetchone() is None:
                folder_id = None

        cursor.execute(
            """
            UPDATE pages
            SET folder_id = %s
            WHERE id = %s
            AND user_id = %s
            """,
            (
                folder_id,
                page_id,
                session["user_id"]
            )
        )

    else:

        if folder_id is not None:

            cursor.execute(
                """
                SELECT id
                FROM folders
                WHERE id = ?
                AND user_id = ?
                """,
                (
                    folder_id,
                    session["user_id"]
                )
            )

            if cursor.fetchone() is None:
                folder_id = None

        cursor.execute(
            """
            UPDATE pages
            SET folder_id = ?
            WHERE id = ?
            AND user_id = ?
            """,
            (
                folder_id,
                page_id,
                session["user_id"]
            )
        )

    conn.commit()
    conn.close()

    return "OK"


# ============================================================
# MYAI PAGE
# ============================================================

@app.route("/ai")
@login_required
def ai_page():

    return render_template(
        "ai.html",
        username=session.get("username", "User")
    )


# ============================================================
# MYAI WEB SEARCH
# ============================================================

def ai_web_search(query):

    try:

        response = requests.get(
            f"{SEARXNG_URL}/search",
            params={
                "q": query,
                "format": "json",
                "categories": "general"
            },
            timeout=10
        )

        response.raise_for_status()

        data = response.json()

        results = []

        for result in data.get("results", [])[:8]:

            title = result.get("title", "")
            content = result.get("content", "")
            url = result.get("url", "")

            if title and url:

                results.append({
                    "title": title,
                    "content": content,
                    "url": url
                })

        return results

    except Exception as e:

        print("MyAI search error:", e)

        return []


# ============================================================
# MYAI CHAT API
# ============================================================

@app.route("/api/ai", methods=["POST"])
@login_required
def ai_chat():

    if not gemini_client:

        return jsonify({
            "error": "Gemini API is not configured."
        }), 500

    data = request.get_json() or {}

    message = data.get(
        "message",
        ""
    ).strip()

    history = data.get(
        "history",
        []
    )

    if not message:

        return jsonify({
            "error": "Please enter a message."
        }), 400


    # Safety filter
    if not safety_check(message):

        return jsonify({
            "error": "I can't help with that request."
        }), 400


    # Internet search
    results = ai_web_search(message)


    search_context = ""

    if results:

        search_context = "INTERNET SEARCH RESULTS:\n\n"

        for i, result in enumerate(results, 1):

            search_context += (
                f"[{i}] {result['title']}\n"
                f"URL: {result['url']}\n"
                f"{result['content']}\n\n"
            )

    else:

        search_context = (
            "No internet search results were available."
        )


    # Conversation history
    conversation = ""

    for item in history[-12:]:

        role = item.get(
            "role",
            "user"
        )

        content = item.get(
            "content",
            ""
        )

        if role == "assistant":

            conversation += (
                f"MyAI: {content}\n"
            )

        else:

            conversation += (
                f"User: {content}\n"
            )


    # Prompt
    prompt = f"""
You are MyAI, the AI assistant built into MySpace.

You are helpful, honest, and clear.

SAFETY RULES:

- Do not help steal passwords, accounts, money, or personal information.
- Do not provide malware, ransomware, spyware, or credential-stealing code.
- Do not help bypass security systems without authorization.
- For cybersecurity questions, focus on defensive and authorized security.
- Do not provide instructions for seriously harming someone.
- If a request is unsafe, briefly explain that you cannot help with it.

INTERNET SEARCH RESULTS:

{search_context}

CONVERSATION:

{conversation}

CURRENT USER MESSAGE:

{message}

Answer the user clearly.

If you use information from the internet results,
mention the relevant source when appropriate.
"""


    # Try models
    last_error = None

    for model in AI_MODELS:

        print(
            f"MyAI trying model: {model}"
        )

        for attempt in range(2):

            try:

                response = gemini_client.models.generate_content(
                    model=model,
                    contents=prompt
                )

                answer = response.text

                if not answer:

                    answer = (
                        "I couldn't generate a response."
                    )

                print(
                    f"MyAI success: {model}"
                )

                return jsonify({
                    "answer": answer,
                    "sources": results,
                    "model": model
                })


            except Exception as e:

                last_error = str(e)

                print(
                    f"MyAI error ({model}):",
                    last_error
                )

                traceback.print_exc()
             
                # Temporary overload
                if (
                    "503" in last_error
                    or "UNAVAILABLE" in last_error
                ):

                    if attempt == 0:

                        time.sleep(2)

                    continue


                # Model unavailable
                if (
                    "404" in last_error
                    or "NOT_FOUND" in last_error
                ):

                    break


                # Other error
                return jsonify({
                    "error": (
                        f"Gemini error: {last_error}"
                    )
                }), 500


    return jsonify({
        "error": (
            "MyAI is temporarily unavailable. "
            "Please try again in a few seconds."
        )
    }), 503


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    if DATABASE_URL:

        print(
            "🌐 MySpace V7 using PostgreSQL"
        )

    else:

        print(
            "💻 MySpace V7 using local SQLite"
        )

    print(
        "🤖 MyAI enabled:",
        bool(GEMINI_API_KEY)
    )

    print()

    print(
        "Open:"
    )

    print(
        "http://127.0.0.1:5000"
    )

    print()

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )
