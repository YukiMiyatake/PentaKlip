"""Native folder picker helper (mocked dialog)."""

from pathlib import Path

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
