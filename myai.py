from flask import Blueprint, render_template, request, jsonify, session
import os
import sqlite3
import requests
from dotenv import load_dotenv
from google import genai

load_dotenv()

myai = Blueprint("myai", __name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

print("MyAI API key loaded:", bool(GEMINI_API_KEY))

SEARXNG_URL = os.environ.get(
    "SEARXNG_URL",
    "http://localhost:8080"
)

DATABASE_URL = os.environ.get("DATABASE_URL")

if GEMINI_API_KEY:
    gemini_client = genai.Client(
        api_key=GEMINI_API_KEY
    )
else:
    gemini_client = None


AI_MODELS = [
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.7-flash",
    "gemini-3.8-flash"
]


# =========================
# DATABASE
# =========================

def is_postgres():
    return bool(DATABASE_URL)


def get_db():

    if DATABASE_URL:
        import psycopg2

        conn = psycopg2.connect(DATABASE_URL)
        return conn

    conn = sqlite3.connect("myspace.db")
    conn.row_factory = sqlite3.Row

    return conn


def setup_chat_database():

    conn = get_db()
    cursor = conn.cursor()

    if is_postgres():

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL DEFAULT 'New Chat',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    else:

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL DEFAULT 'New Chat',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    conn.commit()
    conn.close()


setup_chat_database()


# =========================
# LOGIN CHECK
# =========================

def logged_in():

    return "user_id" in session


# =========================
# INTERNET SEARCH
# =========================

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


# =========================
# AI PAGE
# =========================

@myai.route("/ai")
def ai_page():

    if not logged_in():
        return jsonify({
            "error": "Please log in first."
        }), 401

    return render_template(
        "ai.html",
        username=session.get("username", "")
    )


# =========================
# GET CONVERSATIONS
# =========================

@myai.route("/api/conversations", methods=["GET"])
def get_conversations():

    if not logged_in():
        return jsonify({
            "error": "Please log in first."
        }), 401

    user_id = session["user_id"]

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, title, created_at, updated_at
        FROM conversations
        WHERE user_id = %s
        ORDER BY updated_at DESC
    """ if is_postgres() else """
        SELECT id, title, created_at, updated_at
        FROM conversations
        WHERE user_id = ?
        ORDER BY updated_at DESC
    """, (user_id,))

    rows = cursor.fetchall()

    conn.close()

    conversations = []

    for row in rows:

        conversations.append({
            "id": row[0],
            "title": row[1],
            "created_at": str(row[2]),
            "updated_at": str(row[3])
        })

    return jsonify(conversations)


# =========================
# CREATE CONVERSATION
# =========================

@myai.route("/api/conversations", methods=["POST"])
def create_conversation():

    if not logged_in():
        return jsonify({
            "error": "Please log in first."
        }), 401

    user_id = session["user_id"]

    data = request.get_json(silent=True) or {}

    title = data.get(
        "title",
        "New Chat"
    ).strip()

    if not title:
        title = "New Chat"

    title = title[:100]

    conn = get_db()
    cursor = conn.cursor()

    if is_postgres():

        cursor.execute("""
            INSERT INTO conversations
            (user_id, title)
            VALUES (%s, %s)
            RETURNING id
        """, (user_id, title))

        conversation_id = cursor.fetchone()[0]

    else:

        cursor.execute("""
            INSERT INTO conversations
            (user_id, title)
            VALUES (?, ?)
        """, (user_id, title))

        conversation_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return jsonify({
        "id": conversation_id,
        "title": title
    })


# =========================
# LOAD ONE CONVERSATION
# =========================

@myai.route("/api/conversations/<int:conversation_id>", methods=["GET"])
def load_conversation(conversation_id):

    if not logged_in():
        return jsonify({
            "error": "Please log in first."
        }), 401

    user_id = session["user_id"]

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, title
        FROM conversations
        WHERE id = %s AND user_id = %s
    """ if is_postgres() else """
        SELECT id, title
        FROM conversations
        WHERE id = ? AND user_id = ?
    """, (conversation_id, user_id))

    conversation = cursor.fetchone()

    if not conversation:

        conn.close()

        return jsonify({
            "error": "Chat not found."
        }), 404

    cursor.execute("""
        SELECT role, content, created_at
        FROM messages
        WHERE conversation_id = %s
        ORDER BY id ASC
    """ if is_postgres() else """
        SELECT role, content, created_at
        FROM messages
        WHERE conversation_id = ?
        ORDER BY id ASC
    """, (conversation_id,))

    rows = cursor.fetchall()

    conn.close()

    messages = []

    for row in rows:

        messages.append({
            "role": row[0],
            "content": row[1],
            "created_at": str(row[2])
        })

    return jsonify({
        "id": conversation[0],
        "title": conversation[1],
        "messages": messages
    })


# =========================
# DELETE CONVERSATION
# =========================

@myai.route(
    "/api/conversations/<int:conversation_id>",
    methods=["DELETE"]
)
def delete_conversation(conversation_id):

    if not logged_in():
        return jsonify({
            "error": "Please log in first."
        }), 401

    user_id = session["user_id"]

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id
        FROM conversations
        WHERE id = %s AND user_id = %s
    """ if is_postgres() else """
        SELECT id
        FROM conversations
        WHERE id = ? AND user_id = ?
    """, (conversation_id, user_id))

    conversation = cursor.fetchone()

    if not conversation:

        conn.close()

        return jsonify({
            "error": "Chat not found."
        }), 404

    cursor.execute("""
        DELETE FROM messages
        WHERE conversation_id = %s
    """ if is_postgres() else """
        DELETE FROM messages
        WHERE conversation_id = ?
    """, (conversation_id,))

    cursor.execute("""
        DELETE FROM conversations
        WHERE id = %s AND user_id = %s
    """ if is_postgres() else """
        DELETE FROM conversations
        WHERE id = ? AND user_id = ?
    """, (conversation_id, user_id))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True
    })


# =========================
# AI CHAT
# =========================

@myai.route("/api/ai", methods=["POST"])
def ai_chat():

    if not logged_in():
        return jsonify({
            "error": "Please log in first."
        }), 401

    if not gemini_client:

        return jsonify({
            "error": "MyAI is not configured. Add GEMINI_API_KEY."
        }), 500

    data = request.get_json(silent=True) or {}

    message = data.get(
        "message",
        ""
    ).strip()

    conversation_id = data.get(
        "conversation_id"
    )

    if not message:

        return jsonify({
            "error": "Please enter a message."
        }), 400

    user_id = session["user_id"]

    conn = get_db()
    cursor = conn.cursor()

    # Create a conversation automatically if needed

    if not conversation_id:

        title = message[:50]

        if is_postgres():

            cursor.execute("""
                INSERT INTO conversations
                (user_id, title)
                VALUES (%s, %s)
                RETURNING id
            """, (user_id, title))

            conversation_id = cursor.fetchone()[0]

        else:

            cursor.execute("""
                INSERT INTO conversations
                (user_id, title)
                VALUES (?, ?)
            """, (user_id, title))

            conversation_id = cursor.lastrowid

    # Make sure this chat belongs to this user

    cursor.execute("""
        SELECT id, title
        FROM conversations
        WHERE id = %s AND user_id = %s
    """ if is_postgres() else """
        SELECT id, title
        FROM conversations
        WHERE id = ? AND user_id = ?
    """, (conversation_id, user_id))

    conversation_row = cursor.fetchone()

    if not conversation_row:

        conn.close()

        return jsonify({
            "error": "Chat not found."
        }), 404

    # Save user message

    cursor.execute("""
        INSERT INTO messages
        (conversation_id, role, content)
        VALUES (%s, %s, %s)
    """ if is_postgres() else """
        INSERT INTO messages
        (conversation_id, role, content)
        VALUES (?, ?, ?)
    """, (
        conversation_id,
        "user",
        message
    ))

    # Load previous messages

    cursor.execute("""
        SELECT role, content
        FROM messages
        WHERE conversation_id = %s
        ORDER BY id ASC
    """ if is_postgres() else """
        SELECT role, content
        FROM messages
        WHERE conversation_id = ?
        ORDER BY id ASC
    """, (conversation_id,))

    history_rows = cursor.fetchall()

    conversation_parts = []

    for row in history_rows:

        conversation_parts.append(
            f"{row[0].upper()}: {row[1]}"
        )

    conversation = "\n\n".join(
        conversation_parts
    )

    # Update chat timestamp

    cursor.execute("""
        UPDATE conversations
        SET updated_at = CURRENT_TIMESTAMP
        WHERE id = %s AND user_id = %s
    """ if is_postgres() else """
        UPDATE conversations
        SET updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
    """, (conversation_id, user_id))

    conn.commit()
    conn.close()

    # Search internet

    results = ai_web_search(message)

    search_context_parts = []

    for result in results:

        search_context_parts.append(
            f"Title: {result['title']}\n"
            f"Content: {result['content']}\n"
            f"URL: {result['url']}"
        )

    search_context = "\n\n".join(
        search_context_parts
    )

    # Gemini prompt

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

ANSWER RULES:

- Answer the user clearly and directly.
- Use the internet search results when they are relevant.
- Do not invent facts or URLs.
- If you use information from an internet search result, use the actual URL provided in that result when appropriate.
- When giving the user a website, article, page, video, or other online resource, make it a clickable Markdown link.
- Use this exact format:
  [Website Name](URL)
- Always use the actual URL from the search results.
- Never make up a URL.
- If the user specifically asks for a link, provide the relevant clickable link.
- If multiple useful sources are available, you may provide multiple clickable links.
"""

    last_error = None

    # Gemini fallback

    for model in AI_MODELS:

        print(
            f"MyAI trying model: {model}"
        )

        try:

            response = gemini_client.models.generate_content(
                model=model,
                contents=prompt
            )

            answer = response.text

            print(
                f"MyAI succeeded with model: {model}"
            )

            # Save assistant response

            conn = get_db()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO messages
                (conversation_id, role, content)
                VALUES (%s, %s, %s)
            """ if is_postgres() else """
                INSERT INTO messages
                (conversation_id, role, content)
                VALUES (?, ?, ?)
            """, (
                conversation_id,
                "assistant",
                answer
            ))

            cursor.execute("""
                UPDATE conversations
                SET updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND user_id = %s
            """ if is_postgres() else """
                UPDATE conversations
                SET updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ?
            """, (conversation_id, user_id))

            conn.commit()
            conn.close()

            return jsonify({
                "answer": answer,
                "sources": results,
                "model": model,
                "conversation_id": conversation_id
            })

        except Exception as e:

            error_text = str(e)

            print(
                f"MyAI model {model} failed: "
                f"{error_text}"
            )

            last_error = e

            continue

    return jsonify({
        "error": (
            "MyAI could not get a response from "
            "any available Gemini model. "
            f"Last error: {last_error}"
        )
    }), 503
