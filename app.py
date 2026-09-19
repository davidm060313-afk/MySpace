from flask import Flask, render_template, request, redirect, session
import os
import sqlite3
import psycopg2
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "myspace-local-secret-change-this"
)

DATABASE_URL = os.environ.get("DATABASE_URL")


# =========================
# DATABASE
# =========================

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


# =========================
# LOGIN REQUIRED
# =========================

def login_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if "user_id" not in session:
            return redirect("/login")

        return function(*args, **kwargs)

    return wrapper


# =========================
# HOME
# =========================

@app.route("/")
def home():

    if "user_id" not in session:
        return redirect("/login")

    return redirect("/workspace")


# =========================
# REGISTER
# =========================

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


# =========================
# LOGIN
# =========================

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


# =========================
# LOGOUT
# =========================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")


# =========================
# WORKSPACE
# =========================

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


# =========================
# OPEN PAGE
# =========================

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


# =========================
# NEW PAGE
# =========================

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


# =========================
# SAVE PAGE
# =========================

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


# =========================
# DELETE
# =========================

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


# =========================
# FAVORITE
# =========================

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


# =========================
# CREATE FOLDER
# =========================

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


# =========================
# MOVE PAGE
# =========================

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


# =========================
# START
# =========================

if __name__ == "__main__":

    setup_database()

    if DATABASE_URL:
        print("🌐 MySpace V6 using PostgreSQL")
    else:
        print("💻 MySpace V6 using local SQLite")

    print()
    print("Open:")
    print("http://127.0.0.1:5000")
    print()

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )
