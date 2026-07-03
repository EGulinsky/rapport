"""Local documents + native pickers. Plain file I/O is OS-agnostic and lives
directly here; only pick_folder/pick_file/open_path go through the
FilesProvider (see providers/base.py)."""
from __future__ import annotations

import os
import pathlib

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from agent.providers.base import FilesProvider
from agent.text_extract import SUPPORTED_EXTS, extract_text

router = APIRouter(prefix="/files", tags=["files"])


def get_files_provider() -> FilesProvider:  # overridden in main.py via dependency_overrides
    raise NotImplementedError


@router.get("")
def list_files(folder: str = Query(...), since: float | None = Query(default=None)):
    if not folder or not os.path.isdir(folder):
        raise HTTPException(400, f"Ordner nicht gefunden: {folder}")

    root = pathlib.Path(folder).resolve()
    results = []
    for fpath_obj in root.rglob("*"):
        if not fpath_obj.is_file() or fpath_obj.suffix.lower() not in SUPPORTED_EXTS:
            continue
        try:
            mtime = os.path.getmtime(fpath_obj)
        except OSError:
            continue
        if since is not None and mtime <= since:
            continue
        rel = fpath_obj.relative_to(root)
        subfolder = rel.parts[0] if len(rel.parts) > 1 else ""
        results.append({
            "name": fpath_obj.name,
            "path": str(fpath_obj),
            "text": extract_text(str(fpath_obj)),
            "modified": mtime,
            "subfolder": subfolder,
        })
    return results


@router.get("/browse")
def browse(folder: str = Query(...), subfolder: str = Query(default="")):
    if not folder or not os.path.isdir(folder):
        raise HTTPException(400, f"Ordner nicht gefunden: {folder}")

    root = pathlib.Path(folder).resolve()
    search_root = (root / subfolder) if subfolder else root
    if not search_root.exists():
        raise HTTPException(400, f"Unterordner nicht gefunden: {subfolder}")

    results = []
    try:
        for item in sorted(search_root.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
            try:
                mtime = item.stat().st_mtime
            except OSError:
                mtime = 0
            if item.is_dir():
                results.append({"name": item.name, "path": str(item), "type": "folder", "modified": mtime})
            elif item.is_file() and item.suffix.lower() in SUPPORTED_EXTS:
                results.append({"name": item.name, "path": str(item), "type": "file", "modified": mtime})
    except PermissionError as e:
        raise HTTPException(403, str(e))
    return results


@router.get("/file")
def get_file(path: str = Query(...)):
    if not path or not os.path.isfile(path):
        raise HTTPException(404, f"Datei nicht gefunden: {path}")
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = 0
    return {"name": os.path.basename(path), "path": path, "text": extract_text(path), "modified": mtime}


class OpenRequest(BaseModel):
    path: str


@router.post("/open")
def open_file(body: OpenRequest, provider: FilesProvider = Depends(get_files_provider)):
    if not body.path or not os.path.exists(body.path):
        raise HTTPException(404, f"Datei nicht gefunden: {body.path}")
    provider.open_path(body.path)
    return {"success": True}


@router.get("/pick-folder")
def pick_folder(
    prompt: str = Query(default="Ordner wählen:"),
    provider: FilesProvider = Depends(get_files_provider),
):
    path = provider.pick_folder(prompt)
    if not path:
        raise HTTPException(400, "Kein Ordner ausgewählt")
    return {"path": path}


@router.get("/pick-file")
def pick_file(
    prompt: str = Query(default="Datei wählen:"),
    extensions: str = Query(default="zip,db"),
    provider: FilesProvider = Depends(get_files_provider),
):
    ext_list = [e.strip() for e in extensions.split(",") if e.strip()]
    path = provider.pick_file(prompt, ext_list)
    if not path:
        raise HTTPException(400, "Keine Datei ausgewählt")
    return {"path": path}
