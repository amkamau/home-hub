import mimetypes
import os
import random
import shutil
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse, StreamingHttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST


VIDEO_EXTENSIONS = {".mp4", ".m4v", ".webm", ".mov", ".mkv", ".avi"}


def _safe_path(root: Path, relative: str = "") -> Path:
    # Treat incoming paths as POSIX-style relative paths, regardless of client OS.
    parts = [p for p in PurePosixPath(relative or ".").parts if p not in ("", ".", "/")]
    if any(p == ".." for p in parts):
        raise Http404("Invalid path")
    candidate = root.joinpath(*parts).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        raise Http404("Invalid path")
    return candidate


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _ensure_roots():
    settings.MOVIES_ROOT.mkdir(parents=True, exist_ok=True)
    settings.SHARED_ROOT.mkdir(parents=True, exist_ok=True)


@login_required
def movies(request):
    _ensure_roots()
    current_rel = request.GET.get("path", "")
    current = _safe_path(settings.MOVIES_ROOT, current_rel)
    if not current.exists() or not current.is_dir():
        raise Http404("Folder not found")

    entries = []
    for item in sorted(current.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        rel = _relative(settings.MOVIES_ROOT, item)
        entries.append({
            "name": item.name,
            "relative": rel,
            "is_dir": item.is_dir(),
            "is_video": item.is_file() and item.suffix.lower() in VIDEO_EXTENSIONS,
            "size": item.stat().st_size if item.is_file() else None,
        })

    parent = PurePosixPath(current_rel).parent.as_posix()
    if parent == ".":
        parent = ""
    breadcrumbs = []
    accumulated = []
    for part in PurePosixPath(current_rel).parts:
        if part in ("", ".", "/"):
            continue
        accumulated.append(part)
        breadcrumbs.append({"name": part, "path": "/".join(accumulated)})

    return render(request, "hub/movies.html", {
        "entries": entries, "current_path": current_rel, "parent_path": parent,
        "breadcrumbs": breadcrumbs, "view": request.GET.get("view", "grid"),
    })


def _stream_file_range(request, path: Path):
    size = path.stat().st_size
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    range_header = request.headers.get("Range")
    if not range_header:
        response = FileResponse(open(path, "rb"), content_type=content_type)
        response["Accept-Ranges"] = "bytes"
        response["Content-Length"] = str(size)
        return response

    if not range_header.startswith("bytes=") or "," in range_header:
        return HttpResponse(status=416)

    try:
        start_text, end_text = range_header[6:].split("-", 1)
        if start_text == "":
            suffix = int(end_text)
            if suffix <= 0:
                raise ValueError
            start = max(size - suffix, 0)
            end = size - 1
        else:
            start = int(start_text)
            end = int(end_text) if end_text else size - 1
        if start < 0 or start >= size or end < start:
            raise ValueError
        end = min(end, size - 1)
    except (ValueError, TypeError):
        response = HttpResponse(status=416)
        response["Content-Range"] = f"bytes */{size}"
        return response

    length = end - start + 1
    def iterator():
        with open(path, "rb") as stream:
            stream.seek(start)
            remaining = length
            while remaining:
                chunk = stream.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    response = StreamingHttpResponse(iterator(), status=206, content_type=content_type)
    response["Content-Length"] = str(length)
    response["Content-Range"] = f"bytes {start}-{end}/{size}"
    response["Accept-Ranges"] = "bytes"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
def play_video(request, relative_path):
    path = _safe_path(settings.MOVIES_ROOT, relative_path)
    if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise Http404("Video not found")
    return _stream_file_range(request, path)


@login_required
def playlist(request):
    _ensure_roots()
    folder_rel = request.GET.get("path", "")
    folder = _safe_path(settings.MOVIES_ROOT, folder_rel)
    if not folder.is_dir():
        raise Http404("Folder not found")
    videos = []
    recursive = request.GET.get("recursive", "1") != "0"
    iterator = folder.rglob("*") if recursive else folder.iterdir()
    for item in iterator:
        if item.is_file() and item.suffix.lower() in VIDEO_EXTENSIONS:
            videos.append({"name": item.name, "relative": _relative(settings.MOVIES_ROOT, item)})
    if request.GET.get("shuffle") == "1":
        random.shuffle(videos)
    return render(request, "hub/playlist.html", {"videos": videos, "folder": folder_rel})


@login_required
def files_home(request):
    _ensure_roots()
    current_rel = request.GET.get("path", "")
    current = _safe_path(settings.SHARED_ROOT, current_rel)
    if not current.exists() or not current.is_dir():
        raise Http404("Folder not found")
    entries = []
    for item in sorted(current.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        entries.append({
            "name": item.name, "relative": _relative(settings.SHARED_ROOT, item),
            "is_dir": item.is_dir(), "size": item.stat().st_size if item.is_file() else None,
        })
    parent = PurePosixPath(current_rel).parent.as_posix()
    if parent == ".":
        parent = ""
    return render(request, "hub/files.html", {
        "entries": entries, "current_path": current_rel, "parent_path": parent,
    })


@login_required
def download_file(request, relative_path):
    path = _safe_path(settings.SHARED_ROOT, relative_path)
    if not path.is_file():
        raise Http404("File not found")
    return FileResponse(open(path, "rb"), as_attachment=True, filename=path.name)


@login_required
@require_POST
def file_action(request):
    action = request.POST.get("action", "")
    current_rel = request.POST.get("current_path", "")
    name = request.POST.get("name", "").strip()
    source_rel = request.POST.get("source", "")
    dest_rel = request.POST.get("destination", "").strip()
    current = _safe_path(settings.SHARED_ROOT, current_rel)

    try:
        if not current.is_dir():
            raise ValueError("Folder not found.")

        if action == "upload":
            upload = request.FILES.get("file")
            if not upload:
                raise ValueError("Choose a file first.")
            target = _safe_path(settings.SHARED_ROOT, (Path(current_rel) / Path(upload.name).name).as_posix())
            if target.exists():
                raise ValueError("A file with that name already exists.")
            with open(target, "wb") as out:
                for chunk in upload.chunks():
                    out.write(chunk)
            messages.success(request, "File uploaded.")
        elif action == "mkdir":
            if not name or name in (".", "..") or "/" in name or "\\\\" in name:
                raise ValueError("Enter a valid folder name.")
            target = _safe_path(settings.SHARED_ROOT, (Path(current_rel) / name).as_posix())
            target.mkdir()
            messages.success(request, "Folder created.")
        elif action in {"rename", "delete", "copy", "move"}:
            source = _safe_path(settings.SHARED_ROOT, source_rel)
            if source == settings.SHARED_ROOT.resolve() or not source.exists():
                raise ValueError("Select a valid file or folder.")
            if action == "rename":
                if not name or name in (".", "..") or "/" in name or "\\\\" in name:
                    raise ValueError("Enter a valid new name.")
                target = source.with_name(name)
                if target.exists():
                    raise ValueError("That name already exists.")
                source.rename(target)
                messages.success(request, "Renamed.")
            elif action == "delete":
                if source.is_dir():
                    shutil.rmtree(source)
                else:
                    source.unlink()
                messages.success(request, "Deleted permanently.")
            else:
                destination = _safe_path(settings.SHARED_ROOT, dest_rel)
                if not destination.is_dir():
                    raise ValueError("Destination folder not found.")
                target = destination / source.name
                if target.exists():
                    raise ValueError("A file or folder with that name already exists at the destination.")
                if action == "copy":
                    shutil.copytree(source, target) if source.is_dir() else shutil.copy2(source, target)
                    messages.success(request, "Copied.")
                else:
                    shutil.move(str(source), str(target))
                    messages.success(request, "Moved.")
        else:
            raise ValueError("Unknown action.")
    except (ValueError, OSError, Http404) as exc:
        messages.error(request, str(exc) or "That operation could not be completed.")

    return redirect(f"{request.path.rsplit('/', 2)[0]}/?path={quote(current_rel)}")
