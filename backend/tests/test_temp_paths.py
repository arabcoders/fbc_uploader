import os
import tempfile
from pathlib import Path

from backend.tests import conftest


def test_test_paths_share_one_run_directory():
    run_root = Path(tempfile.gettempdir()).parent

    assert run_root.parent == Path("/tmp/fbc-tests")
    assert Path(os.environ["FBC_CONFIG_PATH"]).parent == run_root
    assert Path(os.environ["FBC_STORAGE_PATH"]).parent == run_root
    assert Path(os.environ["FBC_FRONTEND_EXPORT_PATH"]).parent == run_root


def test_cleanup_test_run_dir_keeps_shared_root(tmp_path):
    shared_root = tmp_path / "fbc-tests"
    run_root = shared_root / "run-123"
    run_root.mkdir(parents=True)

    original_run_dir = conftest.TEST_RUN_DIR
    original_root_dir = conftest.TESTS_TMP_ROOT

    conftest.TEST_RUN_DIR = run_root
    conftest.TESTS_TMP_ROOT = shared_root
    try:
        conftest._cleanup_test_run_dir()
    finally:
        conftest.TEST_RUN_DIR = original_run_dir
        conftest.TESTS_TMP_ROOT = original_root_dir

    assert not run_root.exists()
    assert shared_root.exists()
