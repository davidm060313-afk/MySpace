from flask import Blueprint, render_template, request, jsonify, session
import os
import sqlite3

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

myai = Blueprint("myai", __name__)

# =========================================================
# GEMINI
# =========================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

print("MyAI API key loaded:", bool(GEMINI_API_KEY))

if GEMINI_API_KEY:
    gemini_client = genai.Client(
        api_key=GEMINI_API_KEY
    )
else:
    gemini_client = None


AI_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.7-flash",
    "gemini-3.8-flash"
]


# =========================================================
# DATABASE
# =========================================================

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db():
    if DATABASE_URL:
        import psycopg2

        return psycopg2.connect(DATABASE_URL)

    conn = sqlite3.connect("myspace.db")
    conn.row_factory = sqlite3.Row
    return conn


def setup_chat_database():

    conn = get_db()

    try:
        cur = conn.cursor()

        if DATABASE_URL:

            cur.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL DEFAULT 'New Chat',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id SERIAL PRIMARY KEY,
                    conversation_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

        else:

            cur.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL DEFAULT 'New Chat',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

        conn.commit()

    finally:
        conn.close()


setup_chat_database()


# =========================================================
# USER
# =========================================================

def get_current_user_id():

    user_id = session.get("user_id")

    if not user_id:
        return None

    try:
        return int(user_id)
    except (ValueError, TypeError):
        return None


# =========================================================
# AI PAGE
# =========================================================

@myai.route("/ai")
def ai_page():

    user_id = get_current_user_id()

    if not user_id:
        return "Please log in to use MyAI.", 401

    return render_template(
        "ai.html",
        username=session.get("username", "User")
    )


# =========================================================
# LIST CHATS
# =========================================================

@myai.route("/api/conversations", methods=["GET"])
def get_conversations():

    user_id = get_current_user_id()

    if not user_id:
        return jsonify({
            "error": "You must be logged in."
        }), 401

    conn = get_db()

    try:
        cur = conn.cursor()

        if DATABASE_URL:

            cur.execute("""
                SELECT
                    id,
                    title,
                    created_at,
                    updated_at
                FROM conversations
                WHERE user_id = %s
                ORDER BY updated_at DESC
            """, (user_id,))

            rows = cur.fetchall()

            conversations = []

            for row in rows:

                conversations.append({
                    "id": row[0],
                    "title": row[1],
                    "created_at": str(row[2]),
                    "updated_at": str(row[3])
                })

        else:

            cur.execute("""
                SELECT
                    id,
                    title,
                    created_at,
                    updated_at
                FROM conversations
                WHERE user_id = ?
                ORDER BY updated_at DESC
            """, (user_id,))

            rows = cur.fetchall()

            conversations = [
                {
                    "id": row["id"],
                    "title": row["title"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"]
                }
                for row in rows
            ]

        return jsonify({
            "conversations": conversations
        })

    finally:
        conn.close()


# =========================================================
# CREATE CHAT
# =========================================================

@myai.route("/api/conversations", methods=["POST"])
def create_conversation():

    user_id = get_current_user_id()

    if not user_id:
        return jsonify({
            "error": "You must be logged in."
        }), 401

    data = request.get_json(silent=True) or {}

    title = data.get(
        "title",
        "New Chat"
    ).strip()

    if not title:
        title = "New Chat"

    conn = get_db()

    try:
        cur = conn.cursor()

        if DATABASE_URL:

            cur.execute("""
                INSERT INTO conversations
                    (user_id, title)
                VALUES
                    (%s, %s)
                RETURNING id
            """, (
                user_id,
                title
            ))

            conversation_id = cur.fetchone()[0]

        else:

            cur.execute("""
                INSERT INTO conversations
                    (user_id, title)
                VALUES
                    (?, ?)
            """, (
                user_id,
                title
            ))

            conversation_id = cur.lastrowid

        conn.commit()

        return jsonify({
            "id": conversation_id,
            "title": title
        })

    finally:
        conn.close()


# =========================================================
# GET CHAT
# =========================================================

@myai.route(
    "/api/conversations/<int:conversation_id>",
    methods=["GET"]
)
def get_conversation(conversation_id):

    user_id = get_current_user_id()

    if not user_id:
        return jsonify({
            "error": "You must be logged in."
        }), 401

    conn = get_db()

    try:
        cur = conn.cursor()

        if DATABASE_URL:

            cur.execute("""
                SELECT
                    id,
                    title,
                    created_at,
                    updated_at
                FROM conversations
                WHERE id = %s
                AND user_id = %s
            """, (
                conversation_id,
                user_id
            ))

            conversation = cur.fetchone()

            if not conversation:

                return jsonify({
                    "error": "Chat not found."
                }), 404

            cur.execute("""
                SELECT
                    role,
                    content,
                    created_at
                FROM messages
                WHERE conversation_id = %s
                ORDER BY id ASC
            """, (conversation_id,))

            messages = [
                {
                    "role": row[0],
                    "content": row[1],
                    "created_at": str(row[2])
                }
                for row in cur.fetchall()
            ]

            return jsonify({
                "conversation": {
                    "id": conversation[0],
                    "title": conversation[1],
                    "created_at": str(conversation[2]),
                    "updated_at": str(conversation[3])
                },
                "messages": messages
            })

        else:

            cur.execute("""
                SELECT
                    id,
                    title,
                    created_at,
                    updated_at
                FROM conversations
                WHERE id = ?
                AND user_id = ?
            """, (
                conversation_id,
                user_id
            ))

            conversation = cur.fetchone()

            if not conversation:

                return jsonify({
                    "error": "Chat not found."
                }), 404

            cur.execute("""
                SELECT
                    role,
                    content,
                    created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY id ASC
            """, (conversation_id,))

            messages = [
                {
                    "role": row["role"],
                    "content": row["content"],
                    "created_at": row["created_at"]
                }
                for row in cur.fetchall()
            ]

            return jsonify({
                "conversation": {
                    "id": conversation["id"],
                    "title": conversation["title"],
                    "created_at": conversation["created_at"],
                    "updated_at": conversation["updated_at"]
                },
                "messages": messages
            })

    finally:
        conn.close()


# =========================================================
# DELETE CHAT
# =========================================================

@myai.route(
    "/api/conversations/<int:conversation_id>",
    methods=["DELETE"]
)
def delete_conversation(conversation_id):

    user_id = get_current_user_id()

    if not user_id:
        return jsonify({
            "error": "You must be logged in."
        }), 401

    conn = get_db()

    try:
        cur = conn.cursor()

        if DATABASE_URL:

            cur.execute("""
                SELECT id
                FROM conversations
                WHERE id = %s
                AND user_id = %s
            """, (
                conversation_id,
                user_id
            ))

            if not cur.fetchone():

                return jsonify({
                    "error": "Chat not found."
                }), 404

            cur.execute("""
                DELETE FROM messages
                WHERE conversation_id = %s
            """, (conversation_id,))

            cur.execute("""
                DELETE FROM conversations
                WHERE id = %s
                AND user_id = %s
            """, (
                conversation_id,
                user_id
            ))

        else:

            cur.execute("""
                SELECT id
                FROM conversations
                WHERE id = ?
                AND user_id = ?
            """, (
                conversation_id,
                user_id
            ))

            if not cur.fetchone():

                return jsonify({
                    "error": "Chat not found."
                }), 404

            cur.execute("""
                DELETE FROM messages
                WHERE conversation_id = ?
            """, (conversation_id,))

            cur.execute("""
                DELETE FROM conversations
                WHERE id = ?
                AND user_id = ?
            """, (
                conversation_id,
                user_id
            ))

        conn.commit()

        return jsonify({
            "success": True
        })

    finally:
        conn.close()


# =========================================================
# SAVE MESSAGE
# =========================================================

def save_message(
    conversation_id,
    role,
    content
):

    conn = get_db()

    try:
        cur = conn.cursor()

        if DATABASE_URL:

            cur.execute("""
                INSERT INTO messages
                    (conversation_id, role, content)
                VALUES
                    (%s, %s, %s)
            """, (
                conversation_id,
                role,
                content
            ))

            cur.execute("""
                UPDATE conversations
                SET updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (conversation_id,))

        else:

            cur.execute("""
                INSERT INTO messages
                    (conversation_id, role, content)
                VALUES
                    (?, ?, ?)
            """, (
                conversation_id,
                role,
                content
            ))

            cur.execute("""
                UPDATE conversations
                SET updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (conversation_id,))

        conn.commit()

    finally:
        conn.close()


# =========================================================
# CHAT HISTORY
# =========================================================

def get_chat_history(conversation_id):

    conn = get_db()

    try:
        cur = conn.cursor()

        if DATABASE_URL:

            cur.execute("""
                SELECT role, content
                FROM messages
                WHERE conversation_id = %s
                ORDER BY id ASC
            """, (conversation_id,))

            rows = cur.fetchall()

            history = []

            for row in rows:

                history.append(
                    f"{row[0].upper()}: {row[1]}"
                )

        else:

            cur.execute("""
                SELECT role, content
                FROM messages
                WHERE conversation_id = ?
                ORDER BY id ASC
            """, (conversation_id,))

            rows = cur.fetchall()

            history = []

            for row in rows:

                history.append(
                    f"{row['role'].upper()}: {row['content']}"
                )

        return "\n\n".join(history)

    finally:
        conn.close()


# =========================================================
# UPDATE TITLE
# =========================================================

def update_chat_title(
    conversation_id,
    title
):

    conn = get_db()

    try:
        cur = conn.cursor()

        if DATABASE_URL:

            cur.execute("""
                UPDATE conversations
                SET title = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (
                title,
                conversation_id
            ))

        else:

            cur.execute("""
                UPDATE conversations
                SET title = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                title,
                conversation_id
            ))

        conn.commit()

    finally:
        conn.close()


# =========================================================
# GEMINI REQUEST
# =========================================================

def ask_gemini(
    prompt,
    use_search=True
):

    if not gemini_client:

        raise RuntimeError(
            "GEMINI_API_KEY is not configured."
        )

    last_error = None


    # =====================================================
    # SEARCH VERSION
    # =====================================================

    if use_search:

        search_config = types.GenerateContentConfig(
            tools=[
                types.Tool(
                    google_search=types.GoogleSearch()
                )
            ]
        )

        for model in AI_MODELS:

            print(
                f"MyAI trying Google Search: {model}"
            )

            try:

                response = gemini_client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=search_config
                )

                if response.text:

                    print(
                        f"MyAI Google Search succeeded: {model}"
                    )

                    return (
                        response.text,
                        model,
                        True
                    )

            except Exception as e:

                error_text = str(e)

                print(
                    f"MyAI Google Search failed "
                    f"on {model}: {error_text}"
                )

                last_error = e

                # Search quota is unavailable.
                # Fall through to normal Gemini.
                if (
                    "429" in error_text
                    or "RESOURCE_EXHAUSTED" in error_text
                ):

                    print(
                        "Google Search quota unavailable."
                        " Falling back to normal Gemini."
                    )

                    break


    # =====================================================
    # NORMAL GEMINI FALLBACK
    # =====================================================

    for model in AI_MODELS:

        print(
            f"MyAI trying normal Gemini: {model}"
        )

        try:

            response = gemini_client.models.generate_content(
                model=model,
                contents=prompt
            )

            if response.text:

                print(
                    f"MyAI normal Gemini succeeded: {model}"
                )

                return (
                    response.text,
                    model,
                    False
                )

        except Exception as e:

            error_text = str(e)

            print(
                f"MyAI normal Gemini failed "
                f"on {model}: {error_text}"
            )

            last_error = e

            continue


    raise RuntimeError(
        str(last_error)
    )


# =========================================================
# MAIN AI ROUTE
# =========================================================

@myai.route("/api/ai", methods=["POST"])
def ai_chat():

    user_id = get_current_user_id()

    if not user_id:

        return jsonify({
            "error": "You must be logged in."
        }), 401

    if not gemini_client:

        return jsonify({
            "error": (
                "MyAI is not configured. "
                "Add GEMINI_API_KEY."
            )
        }), 500

    data = request.get_json(
        silent=True
    ) or {}

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

    if not conversation_id:

        return jsonify({
            "error": "Please select or create a chat."
        }), 400

    try:

        conversation_id = int(
            conversation_id
        )

    except (ValueError, TypeError):

        return jsonify({
            "error": "Invalid conversation ID."
        }), 400


    # =====================================================
    # CHECK CHAT OWNERSHIP
    # =====================================================

    conn = get_db()

    try:

        cur = conn.cursor()

        if DATABASE_URL:

            cur.execute("""
                SELECT id, title
                FROM conversations
                WHERE id = %s
                AND user_id = %s
            """, (
                conversation_id,
                user_id
            ))

            conversation = cur.fetchone()

        else:

            cur.execute("""
                SELECT id, title
                FROM conversations
                WHERE id = ?
                AND user_id = ?
            """, (
                conversation_id,
                user_id
            ))

            conversation = cur.fetchone()

    finally:

        conn.close()


    if not conversation:

        return jsonify({
            "error": "Chat not found."
        }), 404


    # =====================================================
    # SAVE USER MESSAGE
    # =====================================================

    save_message(
        conversation_id,
        "user",
        message
    )


    # =====================================================
    # CHAT TITLE
    # =====================================================

    if DATABASE_URL:

        current_title = conversation[1]

    else:

        current_title = conversation["title"]


    if current_title == "New Chat":

        new_title = message[:50]

        if len(message) > 50:

            new_title += "..."

        update_chat_title(
            conversation_id,
            new_title
        )


    # =====================================================
    # HISTORY
    # =====================================================

    conversation_history = get_chat_history(
        conversation_id
    )


    # =====================================================
    # PROMPT
    # =====================================================

    prompt = f"""
You are MyAI, the AI assistant built into MySpace.

You are helpful, honest, friendly, and clear.

You may have access to Google Search.

If search results are available, use them when relevant.

If web search is unavailable, answer normally using your
existing knowledge and clearly avoid pretending that you
looked something up.

IMPORTANT:

- Do not invent facts.
- Do not invent URLs.
- Do not claim you searched if you did not.
- When current information is requested, try to use search.
- If search is unavailable, tell the user that live search
  is temporarily unavailable if that matters to the answer.

SAFETY RULES:

- Do not help steal passwords, accounts, money, or personal
  information.
- Do not provide malware, ransomware, spyware, or
  credential-stealing code.
- Do not help bypass security systems without authorization.
- For cybersecurity questions, focus on defensive and
  authorized security.
- Do not provide instructions for seriously harming someone.
- If a request is unsafe, briefly explain that you cannot help.

CONVERSATION HISTORY:

{conversation_history}

CURRENT USER MESSAGE:

{message}

ANSWER THE USER DIRECTLY.
"""


    # =====================================================
    # ASK GEMINI
    # =====================================================

    try:

        answer, model, used_search = ask_gemini(
            prompt,
            use_search=True
        )

    except Exception as e:

        print(
            "MyAI final error:",
            str(e)
        )

        return jsonify({
            "error": (
                "MyAI could not get a response. "
                f"{str(e)}"
            )
        }), 503


    # =====================================================
    # SAVE AI RESPONSE
    # =====================================================

    save_message(
        conversation_id,
        "assistant",
        answer
    )


    # =====================================================
    # RETURN RESPONSE
    # =====================================================

    return jsonify({
        "answer": answer,
        "sources": [],
        "model": model,
        "web_search": used_search
    })
