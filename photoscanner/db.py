from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional


SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ImageRecord:
    path: str
    sha256: str
    phash: str
    width: int
    height: int
    file_size: int
    mtime_ns: int
    score: float
    embedding: Optional[bytes]
    faces_json: Optional[str]
    objects_json: Optional[str]


class PhotoDB:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def get_duplicate_groups_sha256(self, limit: int = 1, offset: int = 0) -> list[list[ImageRecord]]:
        """Fetch duplicate groups based on SHA256 hash using SQL."""
        # 1. Find SHAs with duplicates
        # deterministic ordering by count desc, then sha
        cursor = self._conn.execute(
            """
            SELECT sha256 
            FROM images 
            GROUP BY sha256 
            HAVING COUNT(*) > 1 
            ORDER BY COUNT(*) DESC, sha256
            LIMIT ? OFFSET ?
            """,
            (limit, offset)
        )
        shas = [row[0] for row in cursor]
        
        groups = []
        for sha in shas:
            # 2. Fetch images for each SHA
            rows = self._conn.execute(
                "SELECT * FROM images WHERE sha256 = ? ORDER BY score DESC", 
                (sha,)
            )
            # Convert to objects
            # Note: row keys must match ImageRecord fields if we unpack, but we used Row factory.
            # We can just map manually or use a helper.
            recs = []
            for r in rows:
                recs.append(self._row_to_record(r))
            groups.append(recs)
            
        return groups

    def _row_to_record(self, row: sqlite3.Row) -> ImageRecord:
        return ImageRecord(
            path=row["path"],
            sha256=row["sha256"],
            phash=row["phash"],
            width=row["width"],
            height=row["height"],
            file_size=row["file_size"],
            mtime_ns=row["mtime_ns"],
            score=row["score"],
            embedding=row["embedding"],
            faces_json=row["faces_json"],
            objects_json=row["objects_json"],
        )

    def close(self) -> None:
        self._conn.close()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS images (
                path TEXT PRIMARY KEY,
                sha256 TEXT NOT NULL,
                phash TEXT NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                file_size INTEGER NOT NULL,
                mtime_ns INTEGER NOT NULL,
                score REAL NOT NULL,
                embedding BLOB,
                faces_json TEXT,
                objects_json TEXT
            );
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS folders (
                path TEXT PRIMARY KEY
            );
            """
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_images_sha256 ON images(sha256)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_images_phash ON images(phash)")
        self._conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)", (str(SCHEMA_VERSION),))
        self._conn.commit()

    def add_folder(self, path: str) -> None:
        self._conn.execute("INSERT OR IGNORE INTO folders(path) VALUES(?)", (path,))

    def remove_folder(self, path: str) -> None:
        self._conn.execute("DELETE FROM folders WHERE path=?", (path,))

    def get_folders(self) -> list[str]:
        cur = self._conn.execute("SELECT path FROM folders ORDER BY path")
        return [row["path"] for row in cur]

    def clear_all(self) -> None:
        self._conn.execute("DELETE FROM images")
        self._conn.execute("DELETE FROM folders")
        self._conn.commit()

    def upsert_image(self, record: ImageRecord) -> None:
        self._conn.execute(
            """
            INSERT INTO images(
                path, sha256, phash, width, height, file_size, mtime_ns, score,
                embedding, faces_json, objects_json
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                sha256=excluded.sha256,
                phash=excluded.phash,
                width=excluded.width,
                height=excluded.height,
                file_size=excluded.file_size,
                mtime_ns=excluded.mtime_ns,
                score=excluded.score,
                embedding=excluded.embedding,
                faces_json=excluded.faces_json,
                objects_json=excluded.objects_json
            """,
            (
                record.path,
                record.sha256,
                record.phash,
                record.width,
                record.height,
                record.file_size,
                record.mtime_ns,
                record.score,
                record.embedding,
                record.faces_json,
                record.objects_json,
            ),
        )

    def delete_image(self, path: str) -> None:
        self._conn.execute("DELETE FROM images WHERE path=?", (path,))

    def update_image_objects(self, path: str, objects_json: str) -> None:
        self._conn.execute("UPDATE images SET objects_json=? WHERE path=?", (objects_json, path))
        self._conn.commit()

    def get_image(self, path: str) -> Optional[ImageRecord]:
        cur = self._conn.execute(
            """
            SELECT path, sha256, phash, width, height, file_size, mtime_ns, score,
                   embedding, faces_json, objects_json
            FROM images
            WHERE path=?
            """,
            (path,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return ImageRecord(
            path=row["path"],
            sha256=row["sha256"],
            phash=row["phash"],
            width=int(row["width"]),
            height=int(row["height"]),
            file_size=int(row["file_size"]),
            mtime_ns=int(row["mtime_ns"]),
            score=float(row["score"]),
            embedding=row["embedding"],
            faces_json=row["faces_json"],
            objects_json=row["objects_json"],
        )

    def commit(self) -> None:
        self._conn.commit()

    def iter_images(self) -> Iterable[ImageRecord]:
        cur = self._conn.execute(
            """
            SELECT path, sha256, phash, width, height, file_size, mtime_ns, score,
                   embedding, faces_json, objects_json
            FROM images
            ORDER BY path
            """
        )
        for row in cur:
            yield ImageRecord(
                path=row["path"],
                sha256=row["sha256"],
                phash=row["phash"],
                width=int(row["width"]),
                height=int(row["height"]),
                file_size=int(row["file_size"]),
                mtime_ns=int(row["mtime_ns"]),
                score=float(row["score"]),
                embedding=row["embedding"],
                faces_json=row["faces_json"],
                objects_json=row["objects_json"],
            )

    def get_images_by_sha256(self, sha256: str) -> list[ImageRecord]:
        cur = self._conn.execute(
            """
            SELECT path, sha256, phash, width, height, file_size, mtime_ns, score,
                   embedding, faces_json, objects_json
            FROM images
            WHERE sha256=?
            ORDER BY score DESC
            """,
            (sha256,),
        )
        return [
            ImageRecord(
                path=row["path"],
                sha256=row["sha256"],
                phash=row["phash"],
                width=int(row["width"]),
                height=int(row["height"]),
                file_size=int(row["file_size"]),
                mtime_ns=int(row["mtime_ns"]),
                score=float(row["score"]),
                embedding=row["embedding"],
                faces_json=row["faces_json"],
                objects_json=row["objects_json"],
            )
            for row in cur
        ]

    def stats(self) -> dict[str, Any]:
        cur = self._conn.execute("SELECT COUNT(*) AS n FROM images")
        n = int(cur.fetchone()["n"])
        return {"images": n}


def dumps_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))