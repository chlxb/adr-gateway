"""Deployment settings for the two ADR-compatible endpoints."""
import os
from pathlib import Path, PureWindowsPath
import tomllib
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    adr_base_url: str = "http://127.0.0.1:18080/api/v1"
    storage_root: Path = PROJECT_ROOT / "var/captures"
    adr_save_root: str | None = None
    host: str = "127.0.0.1"
    port: int = Field(default=18081, ge=1, le=65535)

    @model_validator(mode="after")
    def validate_settings(self):
        url = urlsplit(self.adr_base_url)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.query or url.fragment:
            raise ValueError("adr_base_url must be an HTTP(S) URL without credentials/query")
        self.adr_base_url = self.adr_base_url.rstrip("/")
        self.storage_root = (PROJECT_ROOT / self.storage_root).resolve()
        if self.adr_save_root and not (PureWindowsPath(self.adr_save_root).is_absolute() or Path(self.adr_save_root).is_absolute()):
            raise ValueError('adr_save_root must be an absolute path on the ADR host')
        return self


def load_settings() -> Settings:
    path = Path(os.environ.get("RT_GATEWAY_CONFIG", PROJECT_ROOT / "config/gateway.toml"))
    values = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    for field in Settings.model_fields:
        key = 'RT_GATEWAY_' + field.upper()
        if key in os.environ:
            values[field] = os.environ[key]
    return Settings(**values)
