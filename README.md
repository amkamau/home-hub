# HomeHub (Django)

A small home server for browsing and streaming videos and managing shared files on your local network.

## 1. Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows, activate with:

```powershell
.venv\Scripts\Activate.ps1
```

## 2. Create an administrator

```bash
python manage.py migrate
python manage.py createsuperuser
```

## 3. Start HomeHub

```bash
python manage.py runserver 0.0.0.0:8000
```

Open `http://127.0.0.1:8000/` on the server, or `http://SERVER-LAN-IP:8000/` from another device on your home network.

## Notes
- MKV/AVI support varies by browser.
- Deleting files is permanent; there is no recycle bin.
