from flask import Flask, render_template, request, redirect, session
import sqlite3
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

app.secret_key = "myspace-v5-secret-key-change-me"

DATABASE = "myspace.db"


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# =========================
# DATABASE SETUP
# =========================

def setup_database():

    conn = get_db()

    # USERS
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    # PAGES
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            icon TEXT NOT NULL DEFAULT '📄',
            favorite INTEGER NOT NULL DEFAULT 0,
            folder_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (user_id)
            REFERENCES users(id)
        )
    """)

    # FOLDERS
    conn.execute("""
        CREATE TABLE IF NOT EXISTS folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,

            FOREIGN KEY (user_id)
            REFERENCES users(id)
        )
    """)

    # Upgrade older databases safely
    columns = conn.execute(
        "PRAGMA table_info(pages)"
    ).fetchall()

    column_names = [column["name"] for column in columns]

    if "icon" not in column_names:
        conn.execute("""
            ALTER TABLE pages
            ADD COLUMN icon TEXT NOT NULL DEFAULT '📄'
        """)

    if "favorite" not in column_names:
        conn.execute("""
            ALTER TABLE pages
            ADD COLUMN favorite INTEGER NOT NULL DEFAULT 0
        """)

    if "folder_id" not in column_names:
        conn.execute("""
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

        try:

            cursor = conn.execute(
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

        except sqlite3.IntegrityError:

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

        user = conn.execute(
            """
            SELECT *
            FROM users
            WHERE username = ?
            """,
            (username,)
        ).fetchone()

        conn.close()

        if user and check_password_hash(
            user["password"],
            password
        ):

            session.clear()

            session["user_id"] = user["id"]
            session["username"] = user["username"]

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

    pages = conn.execute(
        """
        SELECT *
        FROM pages
        WHERE user_id = ?
        ORDER BY favorite DESC, updated_at DESC
        """,
        (session["user_id"],)
    ).fetchall()

    folders = conn.execute(
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

    selected = conn.execute(
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

    pages = conn.execute(
        """
        SELECT *
        FROM pages
        WHERE user_id = ?
        ORDER BY favorite DESC, updated_at DESC
        """,
        (session["user_id"],)
    ).fetchall()

    folders = conn.execute(
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

    cursor = conn.execute(
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

    conn.execute(
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

    return redirect(f"/page/{page_id}")


# =========================
# DELETE PAGE
# =========================

@app.route("/delete/<int:page_id>", methods=["POST"])
@login_required
def delete(page_id):

    conn = get_db()

    conn.execute(
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

    return redirect("/workspace")


# =========================
# FAVORITE
# =========================

@app.route("/favorite/<int:page_id>", methods=["POST"])
@login_required
def favorite(page_id):

    conn = get_db()

    page = conn.execute(
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
    ).fetchone()

    if page:

        new_value = 0 if page["favorite"] else 1

        conn.execute(
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

    return redirect(
        request.referrer or "/workspace"
    )


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

        conn.execute(
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
# MOVE PAGE TO FOLDER
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

    if folder_id is not None:

        folder = conn.execute(
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
        ).fetchone()

        if folder is None:
            folder_id = None

    conn.execute(
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

    return redirect(
        request.referrer or "/workspace"
    )


# =========================
# START
# =========================

if __name__ == "__main__":

    setup_database()

    print()
    print("==============================")
    print("          MYSPACE V5")
    print("==============================")
    print()
    print("Open Firefox and go to:")
    print("http://127.0.0.1:5000")
    print()

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )
