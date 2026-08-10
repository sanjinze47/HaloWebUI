import os

import pytest

from open_webui.utils.secret_key import SecretKeyError, resolve_webui_secret_key


def _clear_secret_environment(monkeypatch):
    monkeypatch.delenv("WEBUI_SECRET_KEY", raising=False)
    monkeypatch.delenv("WEBUI_JWT_SECRET_KEY", raising=False)


def test_generated_secret_is_persisted_across_restarts(monkeypatch, tmp_path):
    _clear_secret_environment(monkeypatch)
    data_dir = tmp_path / "data"
    legacy = tmp_path / "legacy-key"

    first = resolve_webui_secret_key(data_dir=data_dir, legacy_path=legacy)
    second = resolve_webui_secret_key(data_dir=data_dir, legacy_path=legacy)

    assert first == second
    assert (data_dir / ".webui_secret_key").read_text(encoding="utf-8") == first
    assert (data_dir / ".webui_secret_key.lock").exists()


def test_legacy_secret_is_migrated_without_deleting_legacy_file(monkeypatch, tmp_path):
    _clear_secret_environment(monkeypatch)
    legacy = tmp_path / ".webui_secret_key"
    legacy.write_text("legacy-secret", encoding="utf-8")

    value = resolve_webui_secret_key(data_dir=tmp_path / "data", legacy_path=legacy)

    assert value == "legacy-secret"
    assert legacy.read_text(encoding="utf-8") == "legacy-secret"
    assert (tmp_path / "data" / ".webui_secret_key").read_text() == "legacy-secret"


def test_conflicting_persistent_and_legacy_secrets_stop_startup(monkeypatch, tmp_path):
    _clear_secret_environment(monkeypatch)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / ".webui_secret_key").write_text("persistent", encoding="utf-8")
    legacy = tmp_path / "legacy"
    legacy.write_text("different", encoding="utf-8")

    with pytest.raises(SecretKeyError, match="Conflicting"):
        resolve_webui_secret_key(data_dir=data_dir, legacy_path=legacy)


def test_explicit_secret_has_priority_over_files(monkeypatch, tmp_path):
    monkeypatch.setenv("WEBUI_SECRET_KEY", "explicit")
    monkeypatch.setenv("WEBUI_JWT_SECRET_KEY", "legacy-env")

    assert (
        resolve_webui_secret_key(
            data_dir=tmp_path / "missing", legacy_path=tmp_path / "legacy"
        )
        == "explicit"
    )
