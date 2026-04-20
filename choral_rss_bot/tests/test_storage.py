import json
from pathlib import Path

from common.storage import JsonFileStorage


def test_load_history_missing_file_returns_empty(tmp_path: Path):
    s = JsonFileStorage(str(tmp_path / "missing.json"))
    assert s.load_history() == []


def test_load_history_malformed_returns_empty(tmp_path: Path):
    p = tmp_path / "hist.json"
    p.write_text("not-json", encoding="utf-8")
    assert JsonFileStorage(str(p)).load_history() == []


def test_save_and_load_roundtrip(tmp_path: Path):
    p = tmp_path / "hist.json"
    s = JsonFileStorage(str(p))
    s.save_history(["a", "b", "c"], max_items=10)
    assert s.load_history() == ["a", "b", "c"]


def test_save_history_trims_to_max_items(tmp_path: Path):
    p = tmp_path / "hist.json"
    s = JsonFileStorage(str(p))
    s.save_history(["a", "b", "c", "d", "e"], max_items=2)
    # keeps the last N
    assert json.loads(p.read_text(encoding="utf-8")) == ["d", "e"]


def test_save_history_preserves_non_ascii(tmp_path: Path):
    p = tmp_path / "hist.json"
    JsonFileStorage(str(p)).save_history(["ひらがな"], max_items=10)
    raw = p.read_text(encoding="utf-8")
    assert "ひらがな" in raw  # ensure_ascii=False


def test_save_then_save_replaces(tmp_path: Path):
    p = tmp_path / "hist.json"
    s = JsonFileStorage(str(p))
    s.save_history(["a"], max_items=10)
    s.save_history(["x", "y"], max_items=10)
    assert s.load_history() == ["x", "y"]
