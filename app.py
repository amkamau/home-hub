import os
import sys
import secrets
import random
import shutil
import sqlite3
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse
from natsort import natsorted

from flask import (
    Flask, abort, flash, redirect, render_template, request,
    send_file, session, url_for
)
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE = Path(__file__).resolve().parent
INSTANCE = BASE / "instance"
INSTANCE.mkdir(parents=True, exist_ok=True)

MOVIE_DIR = Path(os.environ.get("HOMEHUB_MOVIES", str(BASE / "movies"))).resolve()
SHARED_DIR = Path(os.environ.get("HOMEHUB_SHARED", str(BASE / "storage" / "shared"))).resolve()
DB = INSTANCE / "homehub.sqlite3"
KEY_FILE = INSTANCE / "secret_key"

MOVIE_EXTENSIONS = {".mp4", ".m4v", ".webm", ".mov", ".ogv", ".mkv", ".avi"}
MOVIE_DIR.mkdir(parents=True, exist_ok=True)
SHARED_DIR.mkdir(parents=True, exist_ok=True)

if not KEY_FILE.exists():
    KEY_FILE.write_text(secrets.token_hex(32), encoding="utf-8")
try:
    KEY_FILE.chmod(0o600)
except OSError:
    pass

app = Flask(__name__, instance_path=str(INSTANCE))
app.config.update(
    SECRET_KEY=KEY_FILE.read_text(encoding="utf-8").strip(),
    MAX_CONTENT_LENGTH=5 * 1024 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("HOMEHUB_HTTPS") == "1",
)
csrf = CSRFProtect(app)


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
        """)


def create_admin():
    import getpass
    username = input("Admin username: ").strip()
    password = getpass.getpass("Admin password (12+ characters): ")
    if not username or len(username) > 80:
        raise SystemExit("Enter a username between 1 and 80 characters.")
    if len(password) < 12:
        raise SystemExit("Password must be at least 12 characters.")
    with db() as conn:
        try:
            conn.execute(
                "INSERT INTO users(username, password_hash) VALUES (?, ?)",
                (username, generate_password_hash(password)),
            )
        except sqlite3.IntegrityError:
            raise SystemExit("That username already exists.")
    print("Admin account created.")


def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.full_path.rstrip("?")))
        return fn(*args, **kwargs)
    return wrapped


def relative_path(value):
    value = (value or "").replace("\\", "/")
    parts = value.split("/")
    if value.startswith("/") or any(p in (".", "..") for p in parts):
        abort(400)
    return value


def safe_path(root, relative=""):
    """Resolve a relative path without permitting symlink traversal or root escape."""
    root = root.resolve()
    rel = relative_path(relative)
    candidate = root
    for part in Path(rel).parts:
        if part in ("", "."):
            continue
        candidate = candidate / part
        # Check each existing component before resolving it. This prevents a
        # symlink inside an allowed tree from redirecting operations elsewhere.
        if candidate.is_symlink():
            abort(403)
    candidate = candidate.resolve()
    if candidate != root and root not in candidate.parents:
        abort(403)
    return candidate


def movie_files(folder, recursive=False):
    """List supported video files below a folder, excluding symlinks."""
    folder = safe_path(MOVIE_DIR, folder)
    if not folder.is_dir():
        abort(404)
    found = []
    iterator = folder.rglob("*") if recursive else folder.iterdir()
    for path in iterator:
        try:
            if path.is_symlink() or not path.is_file():
                continue
            if path.suffix.lower() not in MOVIE_EXTENSIONS:
                continue
            # rglob can encounter a symlinked directory; ensure resolved path stays inside root.
            resolved = path.resolve()
            if MOVIE_DIR not in resolved.parents:
                continue
            found.append(path.relative_to(MOVIE_DIR).as_posix())
        except OSError:
            continue
    return natsorted(found, key=lambda s: s.lower())


def movie_listing(folder):
    folder_path = safe_path(MOVIE_DIR, folder)
    if not folder_path.is_dir():
        abort(404)
    items = []
    try:
        entries = folder_path.iterdir()
        for path in entries:
            try:
                if path.is_symlink():
                    continue
                if path.is_dir():
                    items.append({
                        "name": path.name,
                        "relative": path.relative_to(MOVIE_DIR).as_posix(),
                        "is_dir": True,
                        "size": None,
                    })
                elif path.is_file() and path.suffix.lower() in MOVIE_EXTENSIONS:
                    items.append({
                        "name": path.name,
                        "relative": path.relative_to(MOVIE_DIR).as_posix(),
                        "is_dir": False,
                        "size": path.stat().st_size,
                    })
            except OSError:
                continue
    except OSError:
        abort(403)
    return sorted(items, key=lambda x: (not x["is_dir"], x["name"].lower()))


def file_listing(folder):
    items = []
    for p in folder.iterdir():
        try:
            if p.is_symlink():
                continue
            items.append({
                "name": p.name,
                "relative": p.relative_to(SHARED_DIR).as_posix(),
                "is_dir": p.is_dir(),
                "size": p.stat().st_size if p.is_file() else None,
            })
        except OSError:
            continue
    return sorted(items, key=lambda x: (not x["is_dir"], x["name"].lower()))


@app.context_processor
def global_template_values():
    return {
        "logged_in": bool(session.get("user_id")),
        "username": session.get("username", ""),
    }


@app.route("/")
def index():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    videos = movie_files("", recursive=True)
    return render_template("index.html", video_count=len(videos))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("index"))
    target = request.args.get("next", "")
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with db() as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            target = request.form.get("next", "")
            parsed = urlparse(target)
            # Avoid open redirects; only allow relative same-site paths.
            if target.startswith("/") and not target.startswith("//") and not parsed.netloc:
                return redirect(target)
            return redirect(url_for("index"))
        flash("Invalid username or password.", "error")
    return render_template("login.html", next_target=target)


@app.post("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/movies")
@login_required
def movies():
    rel = relative_path(request.args.get("path", ""))
    folder = safe_path(MOVIE_DIR, rel)
    if not folder.is_dir():
        abort(404)
    parent = Path(rel).parent.as_posix() if rel else ""
    if parent == ".":
        parent = ""
    items = movie_listing(rel)
    recursive_count = len(movie_files(rel, recursive=True))
    return render_template(
        "movies.html", items=items, current=rel, parent=parent,
        recursive_count=recursive_count, view=request.args.get("view", "list"),
    )


@app.get("/playlist/folder")
@login_required
def playlist_folder():
    rel = relative_path(request.args.get("path", ""))
    recursive = request.args.get("recursive", "1") != "0"
    files = movie_files(rel, recursive=recursive)
    if request.args.get("shuffle") == "1":
        random.shuffle(files)
    if not files:
        flash("No playable videos were found in that folder.", "error")
        return redirect(url_for("movies", path=rel))
    return render_template(
        "player.html", playlist=files, current_index=0,
        playlist_title=Path(rel).name if rel else "All videos",
    )


@app.get("/watch")
@login_required
def watch_query():
    rel = relative_path(request.args.get("path", ""))
    path = safe_path(MOVIE_DIR, rel)
    if not path.is_file() or path.suffix.lower() not in MOVIE_EXTENSIONS:
        abort(404)
    # Individual playback still has a queue of one video.
    return render_template("player.html", playlist=[rel], current_index=0, playlist_title=path.name)


@app.get("/watch/<path:filename>")
@login_required
def watch(filename):
    rel = relative_path(filename)
    path = safe_path(MOVIE_DIR, rel)
    if not path.is_file() or path.suffix.lower() not in MOVIE_EXTENSIONS:
        abort(404)
    return render_template("player.html", playlist=[rel], current_index=0, playlist_title=path.name)


@app.get("/stream/<path:filename>")
@login_required
def stream(filename):
    path = safe_path(MOVIE_DIR, relative_path(filename))
    if not path.is_file() or path.suffix.lower() not in MOVIE_EXTENSIONS:
        abort(404)
    return send_file(path, conditional=True, etag=True)


@app.get("/files")
@login_required
def files():
    rel = relative_path(request.args.get("path", ""))
    folder = safe_path(SHARED_DIR, rel)
    if not folder.is_dir():
        abort(404)
    parent = Path(rel).parent.as_posix() if rel else ""
    if parent == ".":
        parent = ""
    return render_template("files.html", items=file_listing(folder), current=rel, parent=parent)


@app.post("/files/upload")
@login_required
def upload():
    rel = relative_path(request.form.get("path", ""))
    folder = safe_path(SHARED_DIR, rel)
    if not folder.is_dir():
        abort(404)
    uploads = request.files.getlist("files")
    if not uploads or all(not f.filename for f in uploads):
        flash("Choose at least one file.", "error")
        return redirect(url_for("files", path=rel))
    for uploaded in uploads:
        if not uploaded.filename:
            continue
        name = secure_filename(uploaded.filename)
        if not name:
            flash("Skipped a file with an invalid filename.", "error")
            continue
        destination = safe_path(SHARED_DIR, (Path(rel) / name).as_posix())
        if destination.exists():
            flash(f"{name}: already exists; nothing overwritten.", "error")
            continue
        uploaded.save(destination)
    flash("Upload processing finished.", "success")
    return redirect(url_for("files", path=rel))


@app.get("/files/download")
@login_required
def download():
    rel = relative_path(request.args.get("path", ""))
    path = safe_path(SHARED_DIR, rel)
    if not path.is_file():
        abort(404)
    return send_file(path, as_attachment=True, download_name=path.name)


@app.post("/files/create-folder")
@login_required
def create_folder():
    rel = relative_path(request.form.get("path", ""))
    name = secure_filename(request.form.get("name", ""))
    parent = safe_path(SHARED_DIR, rel)
    if not parent.is_dir():
        abort(404)
    if not name:
        abort(400)
    destination = safe_path(SHARED_DIR, (Path(rel) / name).as_posix())
    try:
        destination.mkdir(exist_ok=False)
    except FileExistsError:
        flash("A file or folder with that name already exists.", "error")
    else:
        flash("Folder created.", "success")
    return redirect(url_for("files", path=rel))


def perform_operation(operation):
    rel = relative_path(request.form.get("path", ""))
    new_name = request.form.get("name", "").strip()
    destination_rel = relative_path(request.form.get("destination", ""))
    source = safe_path(SHARED_DIR, rel)
    if source == SHARED_DIR or not source.exists() or source.is_symlink():
        abort(400)

    if operation == "delete":
        if source.is_dir():
            shutil.rmtree(source)
        else:
            source.unlink()
        flash("Item deleted.", "success")
        return redirect(url_for("files", path=source.parent.relative_to(SHARED_DIR).as_posix()))

    if operation == "rename":
        name = secure_filename(new_name)
        if not name:
            abort(400)
        destination = safe_path(
            SHARED_DIR, (source.parent / name).relative_to(SHARED_DIR).as_posix()
        )
    else:
        target_folder = safe_path(SHARED_DIR, destination_rel)
        if not target_folder.is_dir():
            abort(404)
        destination = safe_path(SHARED_DIR, (Path(destination_rel) / source.name).as_posix())

    if destination == source or source in destination.parents:
        abort(400)
    if destination.exists():
        flash("Destination already exists; nothing overwritten.", "error")
        return redirect(url_for("files", path=rel.rpartition("/")[0]))

    if operation == "copy":
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)
    elif operation in ("move", "rename"):
        shutil.move(str(source), str(destination))
    else:
        abort(400)
    flash("Operation completed.", "success")
    return redirect(url_for("files", path=destination.parent.relative_to(SHARED_DIR).as_posix()))


@app.post("/files/rename")
@login_required
def rename_file():
    return perform_operation("rename")


@app.post("/files/copy")
@login_required
def copy_file():
    return perform_operation("copy")


@app.post("/files/move")
@login_required
def move_file():
    return perform_operation("move")


@app.post("/files/delete")
@login_required
def delete_file():
    return perform_operation("delete")


@app.errorhandler(413)
def too_large(_error):
    return "Upload exceeds the 5 GB application limit.", 413


init_db()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "create-admin":
        create_admin()
    else:
        app.run(host="0.0.0.0", port=8000, debug=False)
