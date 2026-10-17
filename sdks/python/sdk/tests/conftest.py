"""
Pytest configuration and fixtures.
Loads environment variables before any tests are collected.
"""

import os
import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from dotenv import load_dotenv

from moss import MossClient

# Load .env from project root.
project_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(project_env_path)

CLOUD_CREDS_WARNING = (
    "Skipping cloud/E2E tests: set real MOSS_TEST_PROJECT_ID and "
    "MOSS_TEST_PROJECT_KEY environment variables to run full integration tests."
)

CLOUD_TEST_FILES = {
    "test_cloud_fallback.py",
    "test_create_index_versions.py",
    "test_e2e.py",
    "test_hot_reload.py",
    "test_metadata_filter_e2e.py",
    "test_search.py",
}


def _has_real_cloud_creds() -> bool:
    project_id = os.getenv("MOSS_TEST_PROJECT_ID", "")
    project_key = os.getenv("MOSS_TEST_PROJECT_KEY", "")
    if not project_id or not project_key:
        return False
    if project_id == "test-project-id" or project_key == "test-project-key":
        return False
    return True


def pytest_configure(config):
    if not _has_real_cloud_creds():
        warnings.warn(CLOUD_CREDS_WARNING)


def pytest_collection_modifyitems(config, items):
    if _has_real_cloud_creds():
        return

    skip_cloud = pytest.mark.skip(reason=CLOUD_CREDS_WARNING)
    for item in items:
        if item.fspath.basename in CLOUD_TEST_FILES:
            item.add_marker(skip_cloud)


@pytest.fixture
def client():
    with (
        patch("moss.client.moss_client.ManageClient") as mock_manage,
        patch("moss.client.moss_client.IndexManager") as mock_mgr,
    ):
        c = MossClient("test-project", "test-key")
        c._manage = mock_manage.return_value
        c._manager = mock_mgr.return_value
        c._manager.has_index = MagicMock(return_value=True)
        yield c


@pytest.fixture
def unloaded_client():
    with (
        patch("moss.client.moss_client.ManageClient") as mock_manage,
        patch("moss.client.moss_client.IndexManager") as mock_mgr,
    ):
        c = MossClient("test-project", "test-key")
        c._manage = mock_manage.return_value
        c._manager = mock_mgr.return_value
        c._manager.has_index = MagicMock(return_value=False)
        yield c
