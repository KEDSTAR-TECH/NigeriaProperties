from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import sqlite3
import os
import hashlib
import html
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

# Active login sessions
sessions = {}


# ==================================================
# DATABASE
# ==================================================

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            verification_status TEXT NOT NULL DEFAULT 'unverified',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            listing_type TEXT NOT NULL,
            price REAL NOT NULL,
            location TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            verification_status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS property_media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            media_type TEXT NOT NULL,
            display_order INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (property_id) REFERENCES properties(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(property_id, user_id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            comment TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reporter_id INTEGER NOT NULL,
            property_id INTEGER,
            reported_user_id INTEGER,
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan_name TEXT NOT NULL,
            start_date TEXT,
            end_date TEXT,
            status TEXT NOT NULL DEFAULT 'inactive'
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            target_type TEXT,
            target_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


# ==================================================
# PASSWORD
# ==================================================

def hash_password(password):
    return hashlib.sha256(
        password.encode("utf-8")
    ).hexdigest()


# ==================================================
# SESSION FUNCTIONS
# ==================================================

def create_session(user_id):
    session_id = secrets.token_urlsafe(32)
    sessions[session_id] = user_id
    return session_id


def get_logged_in_user(handler):

    cookie = handler.headers.get("Cookie")

    if not cookie:
        return None

    session_id = None

    for item in cookie.split(";"):
        item = item.strip()

        if item.startswith("session_id="):
            session_id = item.split(
                "=", 1
            )[1]

    if not session_id:
        return None

    user_id = sessions.get(session_id)

    if not user_id:
        return None

    conn = get_db()

    user = conn.execute("""
        SELECT *
        FROM users
        WHERE id = ?
    """, (user_id,)).fetchone()

    conn.close()

    return user


# ==================================================
# SERVER
# ==================================================

class Handler(BaseHTTPRequestHandler):

    # ------------------------------------------------
    # SEND HTML
    # ------------------------------------------------

    def send_html(self, filename, status=200):

        path = os.path.join(
            BASE_DIR,
            "templates",
            filename
        )

        try:

            with open(path, "rb") as file:
                content = file.read()

            self.send_response(status)

            self.send_header(
                "Content-Type",
                "text/html; charset=utf-8"
            )

            self.end_headers()

            self.wfile.write(content)

        except FileNotFoundError:

            self.send_error(
                404,
                "Page not found"
            )


    # ------------------------------------------------
    # SEND FILE
    # ------------------------------------------------

    def send_file(self, relative_path, content_type):

        path = os.path.join(
            BASE_DIR,
            relative_path
        )

        try:

            with open(path, "rb") as file:
                content = file.read()

            self.send_response(200)

            self.send_header(
                "Content-Type",
                content_type
            )

            self.end_headers()

            self.wfile.write(content)

        except FileNotFoundError:

            self.send_error(
                404,
                "File not found"
            )


    # ==================================================
    # GET
    # ==================================================

    def do_GET(self):

        path = urlparse(
            self.path
        ).path


        # -----------------------------
        # LOGOUT
        # -----------------------------

        if path == "/logout":

            self.logout()

            return


        # -----------------------------
        # DASHBOARD
        # -----------------------------

        if path == "/dashboard":

            user = get_logged_in_user(self)

            if not user:

                self.redirect("/login")

                return

            self.dashboard(user)

            return


        # -----------------------------
        # NORMAL PAGES
        # -----------------------------

        pages = {

            "/": "index.html",

            "/login": "login.html",

            "/register": "register.html",

            "/properties": "properties.html",

            "/property": "property.html",

            "/post-property": "post_property.html"

        }


        if path in pages:

            self.send_html(
                pages[path]
            )

            return


        # -----------------------------
        # CSS
        # -----------------------------

        if path == "/static/style.css":

            self.send_file(
                "static/style.css",
                "text/css"
            )

            return


        # -----------------------------
        # JAVASCRIPT
        # -----------------------------

        if path == "/static/script.js":

            self.send_file(
                "static/script.js",
                "application/javascript"
            )

            return


        self.send_error(
            404,
            "Not found"
        )


    # ==================================================
    # POST
    # ==================================================

    def do_POST(self):

        path = urlparse(
            self.path
        ).path


        if path == "/register":

            self.register_user()

            return


        if path == "/login":

            self.login_user()

            return


        self.send_error(
            404,
            "POST route not found"
        )


    # ==================================================
    # REGISTER
    # ==================================================

    def register_user(self):

        content_length = int(
            self.headers.get(
                "Content-Length",
                0
            )
        )

        body = self.rfile.read(
            content_length
        ).decode("utf-8")

        data = parse_qs(body)

        full_name = data.get(
            "full_name",
            [""]
        )[0].strip()

        email = data.get(
            "email",
            [""]
        )[0].strip().lower()

        password = data.get(
            "password",
            [""]
        )[0]

        role = data.get(
            "role",
            ["user"]
        )[0]


        allowed_roles = [
            "user",
            "landlord",
            "agent"
        ]

        if role not in allowed_roles:
            role = "user"


        if not full_name:

            self.show_message(
                "Registration failed",
                "Please enter your full name.",
                400
            )

            return


        if not email:

            self.show_message(
                "Registration failed",
                "Please enter your email.",
                400
            )

            return


        if len(password) < 6:

            self.show_message(
                "Registration failed",
                "Password must contain at least 6 characters.",
                400
            )

            return


        conn = get_db()

        try:

            conn.execute("""
                INSERT INTO users
                (
                    full_name,
                    email,
                    password_hash,
                    role
                )
                VALUES (?, ?, ?, ?)
            """, (
                full_name,
                email,
                hash_password(password),
                role
            ))

            conn.commit()

            self.show_message(
                "Account created successfully",
                f"Welcome, {html.escape(full_name)}! "
                "Your account has been created."
            )

        except sqlite3.IntegrityError:

            self.show_message(
                "Registration failed",
                "An account with this email already exists.",
                400
            )

        finally:

            conn.close()


    # ==================================================
    # LOGIN
    # ==================================================

    def login_user(self):

        content_length = int(
            self.headers.get(
                "Content-Length",
                0
            )
        )

        body = self.rfile.read(
            content_length
        ).decode("utf-8")

        data = parse_qs(body)

        email = data.get(
            "email",
            [""]
        )[0].strip().lower()

        password = data.get(
            "password",
            [""]
        )[0]


        if not email or not password:

            self.show_message(
                "Login failed",
                "Please enter your email and password.",
                400
            )

            return


        conn = get_db()

        user = conn.execute("""
            SELECT *
            FROM users
            WHERE email = ?
        """, (email,)).fetchone()

        conn.close()


        if user is None:

            self.show_message(
                "Login failed",
                "Incorrect email or password.",
                401
            )

            return


        if user["password_hash"] != hash_password(password):

            self.show_message(
                "Login failed",
                "Incorrect email or password.",
                401
            )

            return


        # Create session

        session_id = create_session(
            user["id"]
        )


        self.send_response(302)

        self.send_header(
            "Set-Cookie",
            f"session_id={session_id}; HttpOnly; Path=/"
        )

        self.send_header(
            "Location",
            "/dashboard"
        )

        self.end_headers()


    # ==================================================
    # DASHBOARD
    # ==================================================

    def dashboard(self, user):

        name = html.escape(
            user["full_name"]
        )

        role = html.escape(
            user["role"]
        )

        page = f"""
<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>Dashboard - NigeriaProperty</title>

<link
    rel="stylesheet"
    href="/static/style.css"
>

</head>


<body>

<header class="navbar">

<a
    class="logo"
    href="/"
>
    NigeriaProperty
</a>

<nav>

<a href="/properties">
    Properties
</a>

<a href="/post-property">
    Post Property
</a>

<a href="/logout">
    Logout
</a>

</nav>

</header>


<main class="section">

<h1>
    Welcome, {name} 👋
</h1>

<p>
    You are logged in as:
    <strong>{role}</strong>
</p>


<div class="cards">

<article class="card">

<h3>
    My Listings
</h3>

<p>
    Your properties will appear here.
</p>

<a href="/post-property">
    Post a property →
</a>

</article>


<article class="card">

<h3>
    Verification
</h3>

<p>
    Account verification status:
    <strong>
        {html.escape(user["verification_status"])}
    </strong>
</p>

</article>


<article class="card">

<h3>
    Subscription
</h3>

<p>
    Your advertising plans will appear here.
</p>

</article>

</div>

</main>

</body>

</html>
"""


        self.send_response(200)

        self.send_header(
            "Content-Type",
            "text/html; charset=utf-8"
        )

        self.end_headers()

        self.wfile.write(
            page.encode("utf-8")
        )


    # ==================================================
    # LOGOUT
    # ==================================================

    def logout(self):

        cookie = self.headers.get(
            "Cookie"
        )

        if cookie:

            for item in cookie.split(";"):

                item = item.strip()

                if item.startswith("session_id="):

                    session_id = item.split(
                        "=",
                        1
                    )[1]

                    sessions.pop(
                        session_id,
                        None
                    )


        self.send_response(302)

        self.send_header(
            "Set-Cookie",
            "session_id=; HttpOnly; Path=/; Max-Age=0"
        )

        self.send_header(
            "Location",
            "/"
        )

        self.end_headers()


    # ==================================================
    # REDIRECT
    # ==================================================

    def redirect(self, location):

        self.send_response(302)

        self.send_header(
            "Location",
            location
        )

        self.end_headers()


    # ==================================================
    # MESSAGE
    # ==================================================

    def show_message(
        self,
        title,
        message,
        status=200
    ):

        page = f"""
<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>{title} - NigeriaProperty</title>

<link
    rel="stylesheet"
    href="/static/style.css"
>

</head>


<body>

<header class="navbar">

<a
    class="logo"
    href="/"
>
    NigeriaProperty
</a>

<a href="/">
    Home
</a>

</header>


<main class="form-page">

<div class="form-card">

<h1>
    {title}
</h1>

<p>
    {message}
</p>

<a
    class="btn"
    href="/"
>
    Return Home
</a>

</div>

</main>

</body>

</html>
"""


        self.send_response(status)

        self.send_header(
            "Content-Type",
            "text/html; charset=utf-8"
        )

        self.end_headers()

        self.wfile.write(
            page.encode("utf-8")
        )


# ==================================================
# START SERVER
# ==================================================

if __name__ == "__main__":

    init_db()

    print(
        "NigeriaProperty server running at "
        "http://127.0.0.1:8000"
    )

    server = HTTPServer(
        ("127.0.0.1", 8000),
        Handler
    )

    server.serve_forever()