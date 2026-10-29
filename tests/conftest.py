"""Isolated preferences and explicit ownership of the native desktop runtime."""
import os
import pytest

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')


@pytest.fixture(scope='session',autouse=True)
def desktop_runtime():
    """Keep Qt alive across tests, then delete windows before WebEngine shuts down.

    Individual tests previously owned the only QApplication reference. Native
    teardown could then run in arbitrary order after pytest printed its summary.
    """
    try:
        from PySide6.QtCore import QCoreApplication,QEvent
        from PySide6.QtWidgets import QApplication
    except ImportError:
        yield None
        return
    application=QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    yield application
    for window in application.topLevelWidgets():
        window.close()
        window.deleteLater()
    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    application.processEvents()
    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)


@pytest.fixture(autouse=True)
def close_test_windows(desktop_runtime):
    """Release each test's native pages instead of accumulating hidden browsers."""
    yield
    if desktop_runtime is None:
        return
    from PySide6.QtCore import QCoreApplication,QEvent
    for window in desktop_runtime.topLevelWidgets():
        window.close()
        window.deleteLater()
    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    desktop_runtime.processEvents()
    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)


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
