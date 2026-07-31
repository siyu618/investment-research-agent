# Semantic Memory — Markdown files with YAML frontmatter
#
# Stores cross-session knowledge: recommendations, user preferences,
# investment rationale. Human-readable and git-trackable.

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from memory.interfaces import MemoryEntry, MemoryProvider, MemoryStats, MemoryTier


class SemanticMemory(MemoryProvider):
    """Markdown file-backed memory for cross-session knowledge.

    Each entry is a markdown file with YAML frontmatter:

        ---
        name: recommendation-000001-20260728
        description: Investment recommendation
        metadata:
          type: recommendation
          score: 0.82
        ---

        **Stock:** 000001.SZ
        **Score:** 0.82
        ...

    Characteristics:
    - Human-readable: files can be opened in any editor
    - Git-trackable: history of knowledge changes
    - Frontmatter: structured metadata for querying
    - Content: free-form markdown for reasoning
    """

    def __init__(self, directory: str = "memory/semantic"):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    @property
    def tier(self) -> MemoryTier:
        return MemoryTier.SEMANTIC

    async def store(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Store a value as a markdown file.

        If value is a dict with 'content' key, uses that as body
        and other keys as frontmatter. Otherwise serializes as JSON.
        """
        filepath = self.directory / f"{self._sanitize_key(key)}.md"

        if isinstance(value, dict) and "content" in value:
            body = value.pop("content")
            metadata = value
        else:
            import json
            body = f"```json\n{json.dumps(value, indent=2, default=str)}\n```"
            metadata = {"type": "data", "stored_at": datetime.now().isoformat()}

        frontmatter_parts = ["---"]
        for k, v in metadata.items():
            frontmatter_parts.append(f"{k}: {v}")
        frontmatter_parts.append("---")

        content = "\n".join(frontmatter_parts) + "\n\n" + body
        filepath.write_text(content)

    async def retrieve(self, key: str) -> Any | None:
        filepath = self.directory / f"{self._sanitize_key(key)}.md"
        if not filepath.exists():
            return None
        content = filepath.read_text()
        parsed = self._parse_frontmatter(content)
        return {
            "metadata": parsed["metadata"],
            "content": parsed["body"],
        }

    async def search(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        results: list[MemoryEntry] = []
        for filepath in sorted(self.directory.glob("*.md"), reverse=True):
            if len(results) >= limit:
                break
            content = filepath.read_text()
            if query.lower() in content.lower():
                parsed = self._parse_frontmatter(content)
                results.append(MemoryEntry(
                    key=filepath.stem,
                    value={
                        "metadata": parsed["metadata"],
                        "content": parsed["body"][:500],
                    },
                    tier=self.tier.value,
                ))
        return results

    async def delete(self, key: str) -> bool:
        filepath = self.directory / f"{self._sanitize_key(key)}.md"
        if filepath.exists():
            filepath.unlink()
            return True
        return False

    async def clear(self, pattern: str = "*") -> int:
        count = 0
        for filepath in self.directory.glob("*.md"):
            if pattern == "*" or filepath.stem.startswith(pattern):
                filepath.unlink()
                count += 1
        return count

    async def stats(self) -> MemoryStats:
        total_size = 0
        count = 0
        for filepath in self.directory.glob("*.md"):
            count += 1
            total_size += filepath.stat().st_size
        return MemoryStats(
            tier=self.tier.value,
            entry_count=count,
            total_size_bytes=total_size,
        )

    @staticmethod
    def _sanitize_key(key: str) -> str:
        """Sanitize a key for use as a filename."""
        sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', key)
        return sanitized[:200]

    @staticmethod
    def _parse_frontmatter(content: str) -> dict:
        """Parse YAML-like frontmatter from markdown content.

        Returns {"metadata": {...}, "body": "..."}.
        Compatible with standard frontmatter format.
        """
        metadata = {}
        body = content

        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                fm_lines = parts[1].strip().split("\n")
                body = parts[2].strip()
                for line in fm_lines:
                    if ":" in line:
                        key, _, val = line.partition(":")
                        metadata[key.strip()] = val.strip()

        return {"metadata": metadata, "body": body}
