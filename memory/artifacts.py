# Artifact Memory — Filesystem-backed artifact storage
#
# Stores generated outputs: reports, charts, data exports.
# Each artifact has a content type and optional metadata.

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from memory.interfaces import MemoryEntry, MemoryProvider, MemoryStats, MemoryTier


class ArtifactMemory(MemoryProvider):
    """Filesystem store for generated artifacts.

    Each artifact is a file on disk with an optional sidecar
    .meta.json file for metadata.

    File layout:
        memory/artifacts/{report_id}/
            report.md             ← The artifact itself
            report.meta.json      ← Metadata (type, created_at, source)
            chart.png             ← Multiple artifacts per report
            chart.meta.json
    """

    def __init__(self, directory: str = "memory/artifacts"):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    @property
    def tier(self) -> MemoryTier:
        return MemoryTier.ARTIFACTS

    async def store(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store an artifact.

        If value is a dict with 'content' and 'type' keys, stores
        the content in a file with the appropriate extension and
        creates a sidecar .meta.json with metadata.

        If value is a string, stores as plain text.
        """
        filepath = self._key_to_path(key, value)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(value, dict) and "content" in value:
            content = value.pop("content")
            # Write metadata sidecar
            meta = {
                "key": key,
                "type": value.get("type", "text"),
                "created_at": datetime.now().isoformat(),
                "metadata": value,
            }
            meta_file = filepath.with_suffix(filepath.suffix + ".meta.json")
            meta_file.write_text(json.dumps(meta, indent=2, default=str))
            # Write content
            if isinstance(content, str):
                filepath.write_text(content)
            else:
                filepath.write_text(json.dumps(content, indent=2, default=str))
        else:
            # Plain text/JSON storage
            if isinstance(value, str):
                filepath.write_text(value)
            else:
                filepath.write_text(json.dumps(value, indent=2, default=str))

    async def retrieve(self, key: str) -> Optional[Any]:
        """Retrieve an artifact by key.

        Returns an Artifact dict with content and metadata.
        """
        # Try direct file first
        filepath = self.directory / key
        if filepath.exists() and filepath.is_file():
            content = filepath.read_text()
            meta = {}
            meta_file = filepath.with_suffix(filepath.suffix + ".meta.json")
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text())
                except json.JSONDecodeError:
                    pass
            return {"content": content, **meta}

        # Try glob for files inside subdirectories
        if "/" not in key:
            # Search entire tree for files matching the key
            for f in self.directory.rglob(f"{key}*"):
                if f.suffix != ".meta.json" and not str(f).endswith(".meta.json"):
                    content = f.read_text()
                    meta = {}
                    meta_file = f.with_suffix(f.suffix + ".meta.json")
                    if meta_file.exists():
                        try:
                            meta = json.loads(meta_file.read_text())
                        except json.JSONDecodeError:
                            pass
                    return {"content": content, **meta}

        return None

    async def search(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        results = []
        for filepath in sorted(self.directory.rglob("*")):
            if len(results) >= limit:
                break
            if filepath.is_file() and filepath.suffix != ".meta.json":
                if query.lower() in filepath.stem.lower() or query.lower() in filepath.suffix.lower():
                    results.append(MemoryEntry(
                        key=str(filepath.relative_to(self.directory)),
                        value={"size": filepath.stat().st_size},
                        tier=self.tier.value,
                    ))
        return results

    async def delete(self, key: str) -> bool:
        """Delete an artifact and its metadata sidecar."""
        # Try exact path first
        filepath = self.directory / key
        if filepath.exists():
            filepath.unlink()
            self._delete_meta(filepath)
            return True

        # Try with common extensions
        for ext in [".md", ".txt", ".json", ".html", ".csv", ".png", ".pdf"]:
            with_ext = self.directory / f"{key}{ext}"
            if with_ext.exists():
                with_ext.unlink()
                self._delete_meta(with_ext)
                return True

        # Try glob inside subdirectories
        for f in self.directory.rglob(f"{key}*"):
            if f.is_file() and f.suffix != ".meta.json":
                f.unlink()
                self._delete_meta(f)
                return True

        return False

    @staticmethod
    def _delete_meta(filepath: Path) -> None:
        """Delete the metadata sidecar for a file if it exists."""
        meta_file = filepath.with_suffix(filepath.suffix + ".meta.json")
        if meta_file.exists():
            meta_file.unlink()

    async def clear(self, pattern: str = "*") -> int:
        count = 0
        for f in self.directory.rglob("*"):
            if f.is_file() and not str(f).endswith(".meta.json"):
                if pattern == "*" or f.stem.startswith(pattern) or f.parent.name == pattern:
                    f.unlink()
                    self._delete_meta(f)
                    count += 1
        # Clean up empty dirs
        for dirpath in sorted(self.directory.rglob("*"), reverse=True):
            if dirpath.is_dir() and not any(dirpath.iterdir()):
                dirpath.rmdir()
        return count

    async def stats(self) -> MemoryStats:
        total_size = 0
        count = 0
        for filepath in self.directory.rglob("*"):
            if filepath.is_file() and filepath.suffix != ".meta.json" and not str(filepath).endswith(".meta.json"):
                count += 1
                total_size += filepath.stat().st_size
        return MemoryStats(
            tier=self.tier.value,
            entry_count=count,
            total_size_bytes=total_size,
        )

    def _key_to_path(self, key: str, value: Any) -> Path:
        """Convert key + value type to a file path.

        Basic: "report-20260729" → "memory/artifacts/report-20260729.txt"
        With type: {"type": "markdown"} → ".md"
        """
        # If value has explicit type, use it for extension
        suffix = ".txt"
        if isinstance(value, dict):
            type_map = {
                "markdown": ".md",
                "chart": ".png",
                "json": ".json",
                "html": ".html",
                "csv": ".csv",
                "pdf": ".pdf",
            }
            content_type = value.get("type", "")
            suffix = type_map.get(content_type, ".txt")

        # If key already has an extension, use it
        path = Path(key)
        if path.suffix:
            return self.directory / key
        return self.directory / f"{key}{suffix}"
