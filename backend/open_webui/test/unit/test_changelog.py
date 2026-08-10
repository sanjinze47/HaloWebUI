from open_webui.env import parse_changelog


def test_parse_changelog_ignores_unreleased_and_keeps_releases():
    changelog = parse_changelog(
        """
## [Unreleased]

### Changed

- Pending behavior

## [1.2.3] - 2026-08-07

### Fixed

- **Upload retry**: Preserved the selected file.
"""
    )

    assert list(changelog) == ["1.2.3"]
    assert changelog["1.2.3"]["date"] == "2026-08-07"
    assert changelog["1.2.3"]["fixed"] == [
        {
            "title": "Upload retry",
            "content": "Preserved the selected file.",
            "raw": (
                "<li><strong>Upload retry</strong>: "
                "Preserved the selected file.</li>"
            ),
        }
    ]


def test_parse_changelog_skips_malformed_release_headings():
    changelog = parse_changelog(
        """
## Release notes

## [1.2.3]

## 1.2.4 - 2026-08-07

## [1.2.5] - 2026-08-08

### Changed
"""
    )

    assert changelog == {"1.2.5": {"date": "2026-08-08", "changed": []}}
