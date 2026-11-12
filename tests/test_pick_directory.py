"""Native folder picker helper (mocked dialog) and fs list API."""

from pathlib import Path

from fastapi.testclient import TestClient

from pentaklip.api.app import app
from pentaklip.settings_store import pick_directory


def test_pick_directory_tkinter_path(monkeypatch, tmp_path: Path) -> None:
    chosen = tmp_path / "picked"
    chosen.mkdir()

    class FakeTk:
        def withdraw(self) -> None:
            return None

        def attributes(self, *args: object, **kwargs: object) -> None:
            _ = args, kwargs

        def destroy(self) -> None:
            return None

    monkeypatch.setattr("tkinter.Tk", FakeTk)
    monkeypatch.setattr(
        "tkinter.filedialog.askdirectory",
        lambda **kwargs: str(chosen),
    )
    assert pick_directory(title="t", initial=str(tmp_path)) == str(chosen.resolve())


def test_pick_directory_cancel(monkeypatch, tmp_path: Path) -> None:
    class FakeTk:
        def withdraw(self) -> None:
            return None

        def attributes(self, *args: object, **kwargs: object) -> None:
            _ = args, kwargs

        def destroy(self) -> None:
            return None

    monkeypatch.setattr("tkinter.Tk", FakeTk)
    monkeypatch.setattr("tkinter.filedialog.askdirectory", lambda **kwargs: "")
    assert pick_directory(initial=str(tmp_path)) is None


def test_fs_list_accepts_suffixes(tmp_path: Path) -> None:
    (tmp_path / "a.rofl").write_bytes(b"x")
    (tmp_path / "b.txt").write_text("y", encoding="utf-8")
    client = TestClient(app)
    response = client.post(
        "/api/fs/list",
        json={"directory": str(tmp_path), "suffixes": [".rofl"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    names = {e["name"] for e in body["entries"] if not e["is_dir"]}
    assert names == {"a.rofl"}
