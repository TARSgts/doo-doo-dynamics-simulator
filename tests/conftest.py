"""Keep desktop tests independent of the user's live Discord and preferences."""
import pytest


@pytest.fixture(autouse=True)
def isolate_discord_presence(tmp_path, monkeypatch):
    try:
        from PySide6.QtCore import QSettings
        import opensim.discord_presence as presence
    except ImportError:
        return
    settings = QSettings(str(tmp_path / "desktop-discord.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(presence, "presence_settings", lambda: settings)
    # Protocol tests explicitly supply their own isolated local server endpoints.
    monkeypatch.setattr(presence, "ipc_endpoints", lambda: [])
