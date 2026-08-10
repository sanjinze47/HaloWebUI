import pathlib
import sys
from types import SimpleNamespace

import pytest


_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.models.skills import SkillModel  # noqa: E402
from open_webui.utils import skill_runtime  # noqa: E402
from open_webui.utils.skill_importer import parse_skill_markdown  # noqa: E402
from open_webui.utils.skill_runtime import (  # noqa: E402
    get_selected_skill_context,
    is_skill_package,
    select_auto_skill_ids,
)


def _skill(
    skill_id: str,
    *,
    name: str,
    description: str = "",
    source: str = "zip",
    content: str = "",
    meta: dict | None = None,
    is_active: bool = True,
):
    return SkillModel(
        id=skill_id,
        user_id="admin-1",
        name=name,
        description=description,
        content=content,
        source=source,
        meta=meta or {"kind": "skill_package"},
        is_active=is_active,
        updated_at=1,
        created_at=1,
    )


def test_imported_skill_markdown_is_marked_as_skill_package():
    payload = parse_skill_markdown(
        """---
name: PDF Toolkit
description: Work with PDF files
tags:
  - pdf
---
# PDF Toolkit

Extract and merge PDFs.
""",
        source="url",
        source_url="https://example.com/SKILL.md",
        synthetic_identifier="url.test",
    )

    assert payload.meta["kind"] == "skill_package"
    assert payload.meta["auto_enabled"] is False
    assert payload.meta["activation"]["keywords"] == ["pdf"]


def test_selected_skill_context_splits_prompt_and_runnable_skills(monkeypatch):
    prompt_skill = _skill(
        "prompt-skill",
        name="Prompt Only",
        source="manual",
        meta={"kind": "prompt_legacy"},
    )
    runnable_skill = _skill(
        "runnable-skill",
        name="Runnable",
        meta={
            "kind": "skill_package",
            "runtime": {"mode": "runnable", "install_status": "ready"},
        },
    )

    monkeypatch.setattr(
        skill_runtime.Skills,
        "get_skill_by_id",
        lambda skill_id: {"prompt-skill": prompt_skill, "runnable-skill": runnable_skill}.get(
            skill_id
        ),
    )
    monkeypatch.setattr(skill_runtime, "can_read_resource", lambda _user, _skill: True)

    context = get_selected_skill_context(
        SimpleNamespace(id="user-1", role="user"),
        ["prompt-skill", "runnable-skill"],
    )

    assert [skill.id for skill in context["prompt_skills"]] == ["prompt-skill"]
    assert [skill.id for skill in context["runnable_skills"]] == ["runnable-skill"]


def test_auto_skill_matching_uses_admin_enabled_visible_packages(monkeypatch):
    enabled = _skill(
        "pdf-skill",
        name="PDF Toolkit",
        description="Extract and merge PDF documents",
        meta={
            "kind": "skill_package",
            "auto_enabled": True,
            "activation": {"keywords": ["pdf", "merge"]},
        },
    )
    disabled = _skill(
        "notes-skill",
        name="Notes",
        description="Apple Notes workflows",
        meta={"kind": "skill_package", "auto_enabled": False},
    )
    legacy = _skill(
        "legacy-skill",
        name="Old Prompt",
        source="manual",
        meta={"kind": "prompt_legacy", "auto_enabled": True},
    )

    monkeypatch.setattr(skill_runtime.Skills, "get_skills", lambda: [disabled, legacy, enabled])
    monkeypatch.setattr(skill_runtime, "can_read_resource", lambda _user, skill: skill.id != "hidden")

    selected = select_auto_skill_ids(
        SimpleNamespace(id="user-1", role="user"),
        [{"role": "user", "content": "帮我 merge 这个 PDF 文件"}],
    )

    assert selected == ["pdf-skill"]


def test_auto_skill_matching_skips_existing_manual_selection(monkeypatch):
    enabled = _skill(
        "pdf-skill",
        name="PDF Toolkit",
        meta={
            "kind": "skill_package",
            "auto_enabled": True,
            "activation": {"keywords": ["pdf"]},
        },
    )

    monkeypatch.setattr(skill_runtime.Skills, "get_skills", lambda: [enabled])
    monkeypatch.setattr(skill_runtime, "can_read_resource", lambda _user, _skill: True)

    selected = select_auto_skill_ids(
        SimpleNamespace(id="user-1", role="user"),
        [{"role": "user", "content": "处理 PDF"}],
        existing_skill_ids=["pdf-skill"],
    )

    assert selected == []
    assert is_skill_package(enabled) is True


def test_disabled_skills_are_excluded_from_auto_and_selected_context(monkeypatch):
    disabled = _skill(
        "disabled",
        name="PDF Toolkit",
        is_active=False,
        meta={
            "kind": "skill_package",
            "auto_enabled": True,
            "activation": {"keywords": ["pdf"]},
        },
    )
    monkeypatch.setattr(skill_runtime.Skills, "get_skills", lambda: [disabled])
    monkeypatch.setattr(
        skill_runtime.Skills, "get_skill_by_id", lambda _skill_id: disabled
    )
    monkeypatch.setattr(skill_runtime, "can_read_resource", lambda *_args: True)

    assert select_auto_skill_ids(
        SimpleNamespace(id="user-1", role="user"),
        [{"role": "user", "content": "process pdf"}],
    ) == []
    context = get_selected_skill_context(
        SimpleNamespace(id="user-1", role="user"), ["disabled"]
    )
    assert context["resolved_ids"] == []


def test_disabled_runnable_skill_cannot_execute():
    disabled = _skill(
        "disabled",
        name="Runner",
        is_active=False,
        meta={
            "kind": "skill_package",
            "runtime": {"mode": "runnable", "install_status": "ready"},
        },
    )

    with pytest.raises(skill_runtime.SkillRuntimeError, match="disabled"):
        skill_runtime.execute_skill_entrypoint(disabled, "run")


def test_failed_skill_asset_stage_keeps_previous_assets(monkeypatch, tmp_path):
    old_root = tmp_path / "old" / "src"
    old_root.mkdir(parents=True)
    (old_root / "SKILL.md").write_text("old", encoding="utf-8")
    skill = _skill(
        "skill-1",
        name="Package",
        meta={
            "kind": "skill_package",
            "package": {
                "archive_file_id": "old-archive",
                "extracted_root": str(old_root),
            },
        },
    )
    payload = SimpleNamespace(
        archive_bytes=b"archive",
        archive_name="package.zip",
        package_files_map={"SKILL.md": b"new"},
        meta={"kind": "skill_package", "import_hash": "new-hash"},
    )
    deleted_paths = []
    monkeypatch.setattr(skill_runtime, "SKILL_SOURCE_CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(
        skill_runtime.Storage,
        "upload_file",
        lambda *_args: (7, "uploaded/package.zip"),
    )
    monkeypatch.setattr(skill_runtime.Storage, "delete_file", deleted_paths.append)
    monkeypatch.setattr(skill_runtime.Files, "insert_new_file", lambda *_args: None)

    with pytest.raises(skill_runtime.SkillRuntimeError, match="save"):
        skill_runtime.save_imported_skill_assets("user-1", skill, payload)

    assert (old_root / "SKILL.md").read_text(encoding="utf-8") == "old"
    assert deleted_paths == ["uploaded/package.zip"]
    assert not list((tmp_path / "cache" / "skill-1").glob(".staging-*"))


def test_skill_assets_require_every_listed_file(monkeypatch, tmp_path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "SKILL.md").write_text("# Skill", encoding="utf-8")
    skill = _skill(
        "skill-1",
        name="Package",
        meta={
            "kind": "skill_package",
            "package": {
                "archive_file_id": "archive-1",
                "extracted_root": str(source_root),
                "files": ["SKILL.md", "scripts/run.py"],
            },
        },
    )
    monkeypatch.setattr(
        skill_runtime.Files,
        "get_file_by_id",
        lambda *_args, **_kwargs: pytest.fail("archive lookup should not run"),
    )

    assert skill_runtime.skill_assets_available(skill) is False


def test_skill_assets_require_archive_blob(monkeypatch, tmp_path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "SKILL.md").write_text("# Skill", encoding="utf-8")
    skill = _skill(
        "skill-1",
        name="Package",
        meta={
            "kind": "skill_package",
            "package": {
                "archive_file_id": "archive-1",
                "extracted_root": str(source_root),
                "files": ["SKILL.md"],
            },
        },
    )
    monkeypatch.setattr(
        skill_runtime.Files,
        "get_file_by_id",
        lambda *_args, **_kwargs: SimpleNamespace(path="archives/skill.zip"),
    )
    monkeypatch.setattr(
        skill_runtime.Storage,
        "get_file",
        lambda _path: (_ for _ in ()).throw(FileNotFoundError("missing blob")),
    )

    assert skill_runtime.skill_assets_available(skill) is False


def test_strict_archive_cleanup_is_idempotent_when_record_is_missing(monkeypatch):
    monkeypatch.setattr(
        skill_runtime.Files,
        "get_file_by_id",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        skill_runtime.Files,
        "delete_file_by_id",
        lambda _id: pytest.fail("missing record must not be deleted again"),
    )

    skill_runtime._delete_archive_file("archive-1", strict=True)


def test_strict_archive_cleanup_keeps_record_when_storage_delete_fails(monkeypatch):
    record_deletes = []
    monkeypatch.setattr(
        skill_runtime.Files,
        "get_file_by_id",
        lambda *_args, **_kwargs: SimpleNamespace(path="archives/skill.zip"),
    )
    monkeypatch.setattr(
        skill_runtime.Storage,
        "delete_file",
        lambda _path: (_ for _ in ()).throw(RuntimeError("storage unavailable")),
    )
    monkeypatch.setattr(
        skill_runtime.Files,
        "delete_file_by_id",
        lambda file_id: record_deletes.append(file_id) or True,
    )

    with pytest.raises(skill_runtime.SkillRuntimeError, match="storage unavailable"):
        skill_runtime._delete_archive_file("archive-1", strict=True)

    assert record_deletes == []
