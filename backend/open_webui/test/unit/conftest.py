import os
import shutil
import sys
import tempfile
from pathlib import Path


_TEST_DATA_DIR = None
if "DATA_DIR" not in os.environ:
    _TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="halowebui-pytest-"))
    os.environ["DATA_DIR"] = str(_TEST_DATA_DIR)


def pytest_sessionfinish(session, exitstatus):
    if _TEST_DATA_DIR is None:
        return

    db_module = sys.modules.get("open_webui.internal.db")
    engine = getattr(db_module, "engine", None)
    if engine is not None:
        engine.dispose()

    shutil.rmtree(_TEST_DATA_DIR, ignore_errors=True)
