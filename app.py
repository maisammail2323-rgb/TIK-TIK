from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
import os
import sqlite3
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "tiktik-secret-key"

UPLOAD_FOLDER = "uploads"
DATABASE = "tiktik.db"

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            bio TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            caption TEXT DEFAULT '',
            hashtags TEXT DEFAULT '',
            username TEXT NOT NULL,
            views INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            UNIQUE(video_id, username)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            comment TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS follows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            follower TEXT NOT NULL,
            following TEXT NOT NULL,
            UNIQUE(follower, following)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS saved (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            UNIQUE(video_id, username)
        )
    """)

    conn.commit()
    conn.close()


init_db()


@app.route("/")
def home():

    search = request.args.get("search", "").strip()

    conn = get_db()

    if search:

        videos = conn.execute("""
            SELECT videos.*,
            (SELECT COUNT(*)
             FROM likes
             WHERE likes.video_id = videos.id) AS like_count,

            (SELECT COUNT(*)
             FROM comments
             WHERE comments.video_id = videos.id) AS comment_count

            FROM videos

            WHERE caption LIKE ?
               OR hashtags LIKE ?
               OR username LIKE ?

            ORDER BY videos.id DESC
        """, (
            f"%{search}%",
            f"%{search}%",
            f"%{search}%"
        )).fetchall()

    else:

        videos = conn.execute("""
            SELECT videos.*,

            (SELECT COUNT(*)
             FROM likes
             WHERE likes.video_id = videos.id) AS like_count,

            (SELECT COUNT(*)
             FROM comments
             WHERE comments.video_id = videos.id) AS comment_count

            FROM videos

            ORDER BY videos.id DESC
        """).fetchall()

    comments = {}

    for video in videos:

        comments[video["id"]] = conn.execute("""
            SELECT *
            FROM comments
            WHERE video_id = ?
            ORDER BY id ASC
        """, (video["id"],)).fetchall()

    current_user = session.get("username")

    conn.close()

    return render_template(
        "index.html",
        videos=videos,
        comments=comments,
        current_user=current_user,
        search=search
    )


@app.route("/register", methods=["POST"])
def register():

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    if not username or not password:
        return redirect(url_for("home"))

    if len(password) < 4:
        return redirect(url_for("home"))

    conn = get_db()

    try:

        conn.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (username, password)
        )

        conn.commit()

        session["username"] = username

    except sqlite3.IntegrityError:

        conn.close()

        return redirect(url_for("home"))

    conn.close()

    return redirect(url_for("home"))


@app.route("/login", methods=["POST"])
def login():

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    conn = get_db()

    user = conn.execute("""
        SELECT *
        FROM users
        WHERE username = ?
        AND password = ?
    """, (username, password)).fetchone()

    conn.close()

    if user:

        session["username"] = username

    return redirect(url_for("home"))


@app.route("/logout")
def logout():

    session.pop("username", None)

    return redirect(url_for("home"))


@app.route("/upload", methods=["POST"])
def upload():

    if "username" not in session:
        return redirect(url_for("home"))

    video = request.files.get("video")

    caption = request.form.get(
        "caption",
        ""
    ).strip()

    hashtags = request.form.get(
        "hashtags",
        ""
    ).strip()

    if video and video.filename:

        filename = secure_filename(
            video.filename
        )

        video.save(
            os.path.join(
                UPLOAD_FOLDER,
                filename
            )
        )

        conn = get_db()

        conn.execute("""
            INSERT INTO videos
            (filename, caption, hashtags, username)
            VALUES (?, ?, ?, ?)
        """, (
            filename,
            caption,
            hashtags,
            session["username"]
        ))

        conn.commit()
        conn.close()

    return redirect(url_for("home"))


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):

    return send_from_directory(
        UPLOAD_FOLDER,
        filename
    )


@app.route("/like/<int:video_id>", methods=["POST"])
def like(video_id):

    if "username" not in session:

        return {
            "success": False
        }

    username = session["username"]

    conn = get_db()

    existing = conn.execute("""
        SELECT *
        FROM likes
        WHERE video_id = ?
        AND username = ?
    """, (
        video_id,
        username
    )).fetchone()

    if existing:

        conn.execute("""
            DELETE FROM likes
            WHERE video_id = ?
            AND username = ?
        """, (
            video_id,
            username
        ))

        liked = False

    else:

        conn.execute("""
            INSERT OR IGNORE INTO likes
            (video_id, username)
            VALUES (?, ?)
        """, (
            video_id,
            username
        ))

        liked = True

    count = conn.execute("""
        SELECT COUNT(*)
        FROM likes
        WHERE video_id = ?
    """, (video_id,)).fetchone()[0]

    conn.commit()
    conn.close()

    return {
        "success": True,
        "liked": liked,
        "count": count
    }


@app.route("/comment/<int:video_id>", methods=["POST"])
def comment(video_id):

    if "username" not in session:
        return redirect(url_for("home"))

    text = request.form.get(
        "comment",
        ""
    ).strip()

    if text:

        conn = get_db()

        conn.execute("""
            INSERT INTO comments
            (video_id, username, comment)
            VALUES (?, ?, ?)
        """, (
            video_id,
            session["username"],
            text
        ))

        conn.commit()
        conn.close()

    return redirect(url_for("home"))


@app.route("/follow/<username>", methods=["POST"])
def follow(username):

    if "username" not in session:
        return redirect(url_for("home"))

    follower = session["username"]

    if follower == username:
        return redirect(url_for("home"))

    conn = get_db()

    existing = conn.execute("""
        SELECT *
        FROM follows
        WHERE follower = ?
        AND following = ?
    """, (
        follower,
        username
    )).fetchone()

    if existing:

        conn.execute("""
            DELETE FROM follows
            WHERE follower = ?
            AND following = ?
        """, (
            follower,
            username
        ))

    else:

        conn.execute("""
            INSERT OR IGNORE INTO follows
            (follower, following)
            VALUES (?, ?)
        """, (
            follower,
            username
        ))

    conn.commit()
    conn.close()

    return redirect(
        url_for(
            "profile",
            username=username
        )
    )


@app.route("/save/<int:video_id>", methods=["POST"])
def save_video(video_id):

    if "username" not in session:

        return {
            "success": False
        }

    username = session["username"]

    conn = get_db()

    existing = conn.execute("""
        SELECT *
        FROM saved
        WHERE video_id = ?
        AND username = ?
    """, (
        video_id,
        username
    )).fetchone()

    if existing:

        conn.execute("""
            DELETE FROM saved
            WHERE video_id = ?
            AND username = ?
        """, (
            video_id,
            username
        ))

        saved_status = False

    else:

        conn.execute("""
            INSERT OR IGNORE INTO saved
            (video_id, username)
            VALUES (?, ?)
        """, (
            video_id,
            username
        ))

        saved_status = True

    conn.commit()
    conn.close()

    return {
        "success": True,
        "saved": saved_status
    }


@app.route("/view/<int:video_id>", methods=["POST"])
def add_view(video_id):

    conn = get_db()

    conn.execute("""
        UPDATE videos
        SET views = views + 1
        WHERE id = ?
    """, (video_id,))

    conn.commit()
    conn.close()

    return {
        "success": True
    }


@app.route("/delete/<int:video_id>", methods=["POST"])
def delete_video(video_id):

    if "username" not in session:
        return redirect(url_for("home"))

    conn = get_db()

    video = conn.execute("""
        SELECT *
        FROM videos
        WHERE id = ?
    """, (video_id,)).fetchone()

    if video and video["username"] == session["username"]:

        filepath = os.path.join(
            UPLOAD_FOLDER,
            video["filename"]
        )

        if os.path.exists(filepath):
            os.remove(filepath)

        conn.execute(
            "DELETE FROM likes WHERE video_id = ?",
            (video_id,)
        )

        conn.execute(
            "DELETE FROM comments WHERE video_id = ?",
            (video_id,)
        )

        conn.execute(
            "DELETE FROM saved WHERE video_id = ?",
            (video_id,)
        )

        conn.execute(
            "DELETE FROM videos WHERE id = ?",
            (video_id,)
        )

        conn.commit()

    conn.close()

    return redirect(url_for("home"))


@app.route("/profile/<username>")
def profile(username):

    conn = get_db()

    user = conn.execute("""
        SELECT *
        FROM users
        WHERE username = ?
    """, (username,)).fetchone()

    if not user:

        conn.close()

        return redirect(url_for("home"))

    videos = conn.execute("""
        SELECT *
        FROM videos
        WHERE username = ?
        ORDER BY id DESC
    """, (username,)).fetchall()

    followers = conn.execute("""
        SELECT COUNT(*)
        FROM follows
        WHERE following = ?
    """, (username,)).fetchone()[0]

    following = conn.execute("""
        SELECT COUNT(*)
        FROM follows
        WHERE follower = ?
    """, (username,)).fetchone()[0]

    conn.close()

    return render_template(
        "profile.html",
        user=user,
        videos=videos,
        followers=followers,
        following=following,
        current_user=session.get("username")
    )


if __name__ == "__main__":
    print("TikTik server starting...")
    print("Open: http://127.0.0.1:5000")

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )