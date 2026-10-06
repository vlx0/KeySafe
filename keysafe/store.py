"""Encrypted local storage for API keys (master password)."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .crypto import MAGIC, InvalidToken, decrypt, derive_key, encrypt, new_salt

STORE_DIR = Path.home() / ".keysafe"
STORE_PATH = STORE_DIR / "keys.bin"

PROVIDERS = (
    "OpenAI",
    "Anthropic",
    "Google",
    "OpenRouter",
    "Groq",
    "Mistral",
    "DeepSeek",
    "Azure",
    "Other",
)


@dataclass
class KeyEntry:
    id: str
    provider: str
    name: str
    key: str
    note: str = ""
    updated: float = field(default_factory=time.time)

    @staticmethod
    def create(provider: str, name: str, key: str, note: str = "") -> "KeyEntry":
        return KeyEntry(
            id=str(uuid.uuid4()),
            provider=(provider or "Other").strip(),
            name=name.strip() or "без имени",
            key=key.strip(),
            note=note.strip(),
        )

    def masked(self) -> str:
        k = self.key.strip()
        if len(k) <= 8:
            return "•" * max(4, len(k))
        return f"{k[:4]}…{k[-4:]}"


def _entries_from_payload(data: dict) -> list[KeyEntry]:
    out: list[KeyEntry] = []
    for item in data.get("entries", []):
        out.append(
            KeyEntry(
                id=item["id"],
                provider=item.get("provider", "Other"),
                name=item.get("name", ""),
                key=item.get("key", ""),
                note=item.get("note", ""),
                updated=float(item.get("updated", time.time())),
            )
        )
    out.sort(key=lambda e: (e.provider.lower(), e.name.lower()))
    return out


class KeyStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or STORE_PATH
        self.entries: list[KeyEntry] = []
        self._key: bytes | None = None
        self._salt: bytes | None = None

    @property
    def unlocked(self) -> bool:
        return self._key is not None

    def exists(self) -> bool:
        return self.path.is_file() and self.path.stat().st_size > 0

    def is_legacy_dpapi(self) -> bool:
        if not self.exists():
            return False
        raw = self.path.read_bytes()
        return not raw.startswith(MAGIC)

    def create(self, master_password: str) -> None:
        if len(master_password) < 6:
            raise ValueError("Пароль слишком короткий (минимум 6 символов)")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._salt = new_salt()
        self._key = derive_key(master_password, self._salt)
        self.entries = []
        self.save()

    def unlock(self, master_password: str) -> None:
        raw = self.path.read_bytes()
        if not raw.startswith(MAGIC):
            raise ValueError("Старый формат хранилища — нужна миграция")
        if len(raw) < 4 + 16 + 16:
            raise ValueError("Файл хранилища повреждён")
        salt = raw[4:20]
        blob = raw[20:]
        key = derive_key(master_password, salt)
        try:
            plain = decrypt(blob, key)
        except InvalidToken as e:
            raise ValueError("Неверный пароль") from e
        data = json.loads(plain.decode("utf-8"))
        self.entries = _entries_from_payload(data)
        self._salt = salt
        self._key = key

    def migrate_from_dpapi(self, master_password: str) -> int:
        """Load legacy DPAPI file and re-encrypt with master password."""
        if len(master_password) < 6:
            raise ValueError("Пароль слишком короткий (минимум 6 символов)")
        from .dpapi import unprotect

        raw = self.path.read_bytes()
        data = json.loads(unprotect(raw).decode("utf-8"))
        entries = _entries_from_payload(data)
        self._salt = new_salt()
        self._key = derive_key(master_password, self._salt)
        self.entries = entries
        self.save()
        return len(entries)

    def change_password(self, old_password: str, new_password: str) -> None:
        if not self.exists():
            raise RuntimeError("Хранилище не создано")
        if len(new_password) < 6:
            raise ValueError("Новый пароль слишком короткий (минимум 6 символов)")
        # verify old
        raw = self.path.read_bytes()
        if not raw.startswith(MAGIC):
            raise ValueError("Неверный формат хранилища")
        salt = raw[4:20]
        blob = raw[20:]
        old_key = derive_key(old_password, salt)
        try:
            plain = decrypt(blob, old_key)
        except InvalidToken as e:
            raise ValueError("Неверный текущий пароль") from e
        data = json.loads(plain.decode("utf-8"))
        self.entries = _entries_from_payload(data)
        self._salt = new_salt()
        self._key = derive_key(new_password, self._salt)
        self.save()

    def lock(self) -> None:
        self.entries = []
        self._key = None
        self._salt = None

    def save(self) -> None:
        if not self._key or not self._salt:
            raise RuntimeError("Хранилище закрыто")
        payload = {
            "version": 2,
            "entries": [asdict(e) for e in self.entries],
        }
        blob = encrypt(json.dumps(payload, ensure_ascii=False).encode("utf-8"), self._key)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_bytes(MAGIC + self._salt + blob)
        tmp.replace(self.path)

    def add(self, entry: KeyEntry) -> None:
        self.entries.append(entry)
        self.entries.sort(key=lambda e: (e.provider.lower(), e.name.lower()))
        self.save()

    def update(self, entry: KeyEntry) -> None:
        found = False
        for i, cur in enumerate(self.entries):
            if cur.id == entry.id:
                entry.updated = time.time()
                self.entries[i] = entry
                found = True
                break
        if not found:
            raise KeyError(entry.id)
        self.entries.sort(key=lambda e: (e.provider.lower(), e.name.lower()))
        self.save()

    def remove(self, entry_id: str) -> None:
        self.entries = [e for e in self.entries if e.id != entry_id]
        self.save()

    def get(self, entry_id: str) -> KeyEntry | None:
        for e in self.entries:
            if e.id == entry_id:
                return e
        return None
