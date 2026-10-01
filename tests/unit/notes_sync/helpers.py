from datetime import UTC, datetime
from pathlib import Path

from jouskaio_api.modules.notes_sync.domain import SourceNote


def make_note(root: Path, key: str, content: bytes) -> SourceNote:
    path = root / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return SourceNote(key=key, path=path, modified_at=datetime.now(UTC))
