# HomeHub — Flask home server

A small Flask application for a private LAN server. It provides:
- Admin-created accounts and a login-first dashboard.
- Movie/video folder browsing in list and grid layouts.
- Folder playlists, including recursive subfolder playback, shuffle, and queue controls.
- Individual playback with browser byte-range seeking where supported.
- A shared-file manager with upload, download, folder creation, rename, copy, move, and delete.
- CSRF protection on forms and session cookies configured as HTTP-only.

## Requirements

- Python 3.10 or newer (Python 3.12 is a sensible target).
- A modern browser.
- Video files stored under `movies/` by default.
- Shared files stored under `storage/shared/` by default.

The browser's native video support varies. MP4 files encoded with H.264 video and AAC audio are broadly compatible. Some MKV/AVI files and codecs won't play natively in a browser; this version does not transcode media.

## Install

From the project directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Create the first administrator account:

```bash
python app.py create-admin
```

Choose a username and a unique password of at least 12 characters. There is no public registration route. Create additional accounts by running this command again with a different username.

## Run

```bash
source .venv/bin/activate
python app.py
```

Then open `http://127.0.0.1:8000` on the server itself, or `http://SERVER-LAN-IP:8000` from another device on the same network. Find the server's LAN address with `hostname -I` on Linux.

The app binds to `0.0.0.0:8000` to allow LAN devices to connect. Permit port 8000 in your host firewall only on the trusted home LAN. Do not port-forward this development server directly to the public internet.

## Configure media and shared directories

By default, folders are inside the project:

```text
lan-home-server/
├── movies/              # video library; folders become browsable
├── storage/shared/      # file-manager root
├── instance/            # SQLite database and secret key
├── templates/
├── static/
├── app.py
└── requirements.txt
```

You can point to other directories with environment variables:

```bash
export HOMEHUB_MOVIES="/path/to/video-library"
export HOMEHUB_SHARED="/path/to/shared-files"
python app.py
```

The process user must have permission to read media and to modify the shared directory. Video extensions currently recognized: `.mp4`, `.m4v`, `.webm`, `.mov`, `.ogv`, `.mkv`, and `.avi`.

## Using the movie browser

- Click a folder to browse inside it.
- Use the **List / Grid** switch to change layout.
- Select **Play folder + subfolders** to queue every supported video below the current folder.
- In list view, use **Play all** on a folder. You can also right-click a folder to open the context menu for current-folder playback, recursive playback, or shuffle.
- Click a video to play it individually.
- The player queue supports selecting a video, Previous/Next, and automatically advancing when a video ends.
- Playlists are temporary and are generated from the current filesystem each time; they are not saved in SQLite.

## Notes and safety

- Every movie, player, stream, and file-manager route requires login. `/login` is the only public application page.
- Keep `instance/secret_key` private and keep the `instance/` directory out of version control. It is created automatically with restrictive file permissions where supported.
- Use HTTPS and set `HOMEHUB_HTTPS=1` only when the app is actually served behind correctly configured HTTPS. Otherwise secure cookies will not be sent by ordinary HTTP.
- Flask's built-in server is suitable for local development/testing, not a hardened public deployment. For a more permanent LAN deployment, run behind a production WSGI server and reverse proxy.
- The file manager can permanently delete folders and their contents. There is no recycle bin in this version.
- Large uploads are limited to 5 GB by Flask configuration; reverse proxies may have their own limits.
- Do not expose this service directly to the internet without additional deployment hardening, HTTPS, firewall rules, and a review of the threat model.
