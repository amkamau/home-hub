# HomeHub 🏠

A simple Flask home server for watching videos and managing files on your local network.

## Getting started

**1. Install the dependencies**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**2. Create an admin account**

```bash
python app.py create-admin
```

Choose a username and a password of at least 12 characters.

**3. Start HomeHub**

```bash
python app.py
```

Open **http://127.0.0.1:8000** on the server, or **http://SERVER-LAN-IP:8000** from another device on your home network.

## What you can do

- 🎬 Browse videos in list or grid view.
- ▶️ Play a folder, including videos in subfolders, shuffle, and manage the playback queue.
- 📁 Upload, download, organize, copy, move, rename, and delete shared files.
- 🔐 Keep your content private with login-protected pages and admin-created accounts.

## Where your files go

- `movies/` — your video library.
- `storage/shared/` — files managed through HomeHub.
- `instance/` — your database and secret key. Keep this folder private.

You can use different directories by setting `HOMEHUB_MOVIES` and `HOMEHUB_SHARED` before starting the app.

## A few tips

- Use HomeHub only on a trusted home network. **Don't expose the development server directly to the internet.**
- MP4 videos are generally the most browser-friendly. Some MKV and AVI files may not play.
- Deleted files and folders cannot be recovered through HomeHub.
- Playlists are temporary and aren't saved between sessions.
