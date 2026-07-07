"""Library totals and backup coverage, via in-process osxphotos.

Slow (PhotosDB load is minutes on a 20k-photo library) — always called
from the backup background thread, never the UI thread. The shared filter
runs in Python: the PhotosDB query kwargs for it are not trusted (brief).
"""

from __future__ import annotations

from pathlib import Path

EXPORT_DB_NAME = ".osxphotos_export.db"


def library_stats() -> dict:
    """Totals for the backup's scope: not-shared photos + movies."""
    from osxphotos import PhotosDB

    photos = [p for p in PhotosDB().photos(images=True, movies=True) if not p.shared]
    return {
        "library_total": len(photos),
        "missing": sum(1 for p in photos if p.ismissing),
        "uuids": {p.uuid for p in photos},
    }


def exported_uuids(dest: str | Path) -> set[str] | None:
    """UUIDs the export db has ever seen; None when unavailable (share down)."""
    from osxphotos.export_db import ExportDB

    db_path = Path(dest) / EXPORT_DB_NAME
    if not db_path.exists():
        return None
    return set(ExportDB(dbfile=db_path, export_dir=dest).get_previous_uuids())


def coverage_counts(exported: set[str] | None, library_uuids: set[str]) -> dict:
    """Intersect with the live library: ExportDB remembers deleted photos,
    so its raw count can exceed the library total."""
    return {
        "exported_in_library": len(exported & library_uuids) if exported is not None else None,
        "library_total": len(library_uuids),
    }


def gather(dest: str | Path) -> dict:
    """Everything status.json needs: library totals + coverage."""
    lib = library_stats()
    uuids = lib.pop("uuids")
    return {
        "library": lib,
        "coverage": coverage_counts(exported_uuids(dest), uuids),
    }
