"""Checks for the service split: installed imports and cwd-independent resources."""
from importlib import import_module
from pathlib import Path

from unlockops.settings import PROJECT_ROOT, project_path
from unlockops_rag.search import DocumentIndex


def test_all_service_packages_are_importable():
    for name, folder in (
        ("unlockops.graph", "agent"),
        ("unlockops_rag.search", "rag"),
        ("unlockops_mcp.policy", "mcp"),
        ("unlockops_mcp.business", "mcp"),
        ("unlockops_worker.__main__", "worker"),
    ):
        module = import_module(name)
        assert Path(module.__file__).is_relative_to(PROJECT_ROOT / folder)


def test_data_and_checkpoint_paths_do_not_depend_on_terminal_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", "./data")
    monkeypatch.setenv("CHECKPOINT_PATH", "./data/checkpoints/debug.sqlite")
    monkeypatch.setenv("EMBEDDING_BASE_URL", "")
    monkeypatch.setenv("EMBEDDING_MODEL", "")
    data = project_path("DATA_DIR", "data")
    assert data == PROJECT_ROOT / "data"
    assert project_path("CHECKPOINT_PATH", "unused") == PROJECT_ROOT / "data/checkpoints/debug.sqlite"
    assert DocumentIndex(data / "policy_corpus.md", "policy").read("POL-03")


def test_absolute_path_overrides_are_preserved(tmp_path, monkeypatch):
    monkeypatch.setenv("CHECKPOINT_PATH", str(tmp_path / "debug.sqlite"))
    assert project_path("CHECKPOINT_PATH", "unused") == tmp_path / "debug.sqlite"
