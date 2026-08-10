from open_webui.utils.file_lock import exclusive_file_lock


def test_exclusive_file_lock_releases_and_keeps_lock_file(tmp_path):
    lock_path = tmp_path / "state.lock"

    with exclusive_file_lock(lock_path):
        assert lock_path.exists()

    with exclusive_file_lock(lock_path):
        assert lock_path.stat().st_size >= 1
