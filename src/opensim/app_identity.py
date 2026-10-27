import ctypes
import os
from pathlib import Path


APPLICATION_ID = "TARSgts.DooDooDynamicsSimulator.1"
ICON_PATH = Path(__file__).with_name("assets") / "app-icon.ico"


def set_process_identity():
    if os.name == "nt":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APPLICATION_ID)
