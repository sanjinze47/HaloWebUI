from __future__ import annotations

import os
import secrets
from pathlib import Path

from open_webui.utils.file_lock import exclusive_file_lock


class SecretKeyError(RuntimeError):
    pass


def _default_data_dir() -> Path:
    backend_dir = Path(__file__).resolve().parents[2]
    return Path(os.getenv("DATA_DIR", backend_dir / "data")).resolve()


def _default_legacy_paths() -> list[Path]:
    return [
        Path(__file__).resolve().parents[2] / ".webui_secret_key",
        Path.cwd() / ".webui_secret_key",
    ]


def _validate_key(value: str, source: Path | str) -> str:
    value = value.strip()
    if not value or "\0" in value:
        raise SecretKeyError(f"WEBUI secret key from {source} is empty or invalid.")
    return value


def _read_key(path: Path) -> str:
    try:
        return _validate_key(path.read_text(encoding="utf-8"), path)
    except OSError as exc:
        raise SecretKeyError(f"Unable to read WEBUI secret key from {path}: {exc}") from exc


def _write_key_atomic(path: Path, value: str) -> None:
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
    )
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name != "nt":
            temporary.chmod(0o600)
        os.replace(temporary, path)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise SecretKeyError(f"Unable to persist WEBUI secret key to {path}: {exc}") from exc


def resolve_webui_secret_key(
    *, data_dir: Path | None = None, legacy_path: Path | None = None
) -> str:
    explicit = os.getenv("WEBUI_SECRET_KEY")
    if explicit is not None and explicit.strip():
        return _validate_key(explicit, "WEBUI_SECRET_KEY")

    legacy_env = os.getenv("WEBUI_JWT_SECRET_KEY")
    if legacy_env is not None and legacy_env.strip():
        return _validate_key(legacy_env, "WEBUI_JWT_SECRET_KEY")

    data_dir = Path(data_dir or _default_data_dir()).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    key_path = data_dir / ".webui_secret_key"
    legacy_paths = (
        [Path(legacy_path).resolve()]
        if legacy_path is not None
        else [path.resolve() for path in _default_legacy_paths()]
    )
    legacy_paths = list(dict.fromkeys(legacy_paths))

    with exclusive_file_lock(data_dir / ".webui_secret_key.lock"):
        persistent_key = _read_key(key_path) if key_path.exists() else None
        legacy_values = {
            path: _read_key(path)
            for path in legacy_paths
            if path != key_path and path.exists()
        }
        distinct_legacy_values = set(legacy_values.values())
        if len(distinct_legacy_values) > 1:
            raise SecretKeyError(
                "Conflicting legacy WEBUI secret keys exist at: "
                + ", ".join(str(path) for path in legacy_values)
            )
        legacy_key = next(iter(distinct_legacy_values), None)
        if persistent_key and legacy_key and persistent_key != legacy_key:
            raise SecretKeyError(
                f"Conflicting WEBUI secret keys exist at {key_path} and a legacy location."
            )
        if persistent_key:
            return persistent_key
        if legacy_key:
            _write_key_atomic(key_path, legacy_key)
            return legacy_key

        generated = secrets.token_urlsafe(32)
        _write_key_atomic(key_path, generated)
        return generated


def ensure_webui_secret_key(**kwargs) -> str:
    key = resolve_webui_secret_key(**kwargs)
    os.environ["WEBUI_SECRET_KEY"] = key
    return key


if __name__ == "__main__":
    print(ensure_webui_secret_key())
