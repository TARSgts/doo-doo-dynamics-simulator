"""Application themes; shared by every desktop panel."""

STYLE = """
QMainWindow { background: #e8edf3; }
QWidget { color: #27374a; font-family: 'Segoe UI'; font-size: 12px; }
QToolTip { color:#27374a; background:#fffbe8; border:1px solid #9aaec7; padding:6px; }
QMenuBar { background: #172b43; color: #e7eff8; padding: 4px; }
QMenuBar::item:selected { background: #304961; }
QMenu { background: white; }
QTabWidget::pane { border: 0; background: #f6f8fb; }
QTabBar::tab { background: #e5eaf1; padding: 9px 19px; color: #45576c; }
QTabBar::tab:selected { background: #fff; color: #1c344f; border-top: 3px solid #d99530; }
QTabWidget#CommandRibbon QTabBar::tab { padding:5px 13px; }
QTabWidget#CommandRibbon QToolButton { padding:5px 10px; }
QToolButton { background: transparent; border: 1px solid transparent; padding: 9px 15px; border-radius: 4px; }
QToolButton:hover { background: #e5edf7; border-color: #cad7e6; }
QToolButton:disabled { color: #a6aeba; background: #eff1f4; }
QPushButton { background: #f7f9fc; border: 1px solid #c6d0dc; border-radius: 4px; padding: 7px 13px; }
QPushButton:hover { background: #e8f0fa; }
QPushButton:disabled { color: #a8b0ba; background: #f1f3f6; border-color: #e2e6ec; }
QDockWidget { font-weight: 600; }
QDockWidget::title { background: #dce4ee; padding: 8px; }
QTreeWidget { border: 0; background: #fbfcfe; outline: 0; }
QTreeWidget::item { padding: 5px 2px; }
QTreeWidget::item:selected { background: #dceafa; color: #163f6b; }
QDoubleSpinBox, QSpinBox, QComboBox { padding: 5px; border: 1px solid #cbd4df; background: white; border-radius: 3px; }
QLineEdit, QListWidget { padding:5px; border:1px solid #cbd4df; background:white; border-radius:3px; }
QLineEdit:focus { border-color:#d99530; }
QPlainTextEdit { border: 0; background: #f9fbfd; font-family: Consolas; font-size: 11px; }
QStatusBar { background: #172b43; color: #e2edf7; }
QStatusBar QLabel { color: #e2edf7; padding: 3px 10px; }
QProgressBar { border:1px solid #9aaec7; border-radius:4px; background:#dbe5f0; text-align:center; color:#27374a; }
QProgressBar::chunk { background:#d99b35; border-radius:3px; }
QSplitter::handle { background: #d5dde7; }
QSplitter::handle:hover { background:#d99530; }
QWidget#ViewportTools { background:#f8fafc; }
QLabel#DetailsHeading { background:#dce5ef; padding:9px; font-weight:600; }
QLabel#ResultCard { background:white; color:#31485f; border:1px solid #d9e2ec; padding:5px 10px; border-radius:5px; }
QWidget#DetailsPanel, QScrollArea#PropertiesScroll { background:#f2f5fa; }
QScrollBar:vertical { background:#e0e7f0; width:10px; margin:0; }
QScrollBar::handle:vertical { background:#9caec5; min-height:24px; border-radius:4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QWidget#ApplicationHeader { background:#172b43; border-bottom:2px solid #d99530; }
QLabel#ApplicationTitle { color:#edf4ff; font-size:14px; font-weight:600; background:transparent; }
"""

DARK_STYLE = """
QMainWindow, QWidget { background:#121b2b; color:#d8e4f1; }
QToolTip { color:#e6eefb; background:#22334a; border:1px solid #6b819c; }
QMenuBar, QStatusBar { background:#0d1420; color:#dce6f4; }
QProgressBar { border-color:#405674; background:#17263b; color:#e6eefb; }
QMenu { background:#1c293d; border:1px solid #35445b; }
QMenu::item:selected { background:#2e4565; }
QTabWidget::pane { background:#182538; }
QTabBar::tab { background:#142034; color:#9faec2; }
QTabBar::tab:selected { background:#20324b; color:#f1c576; border-top-color:#dba24a; }
QToolButton { background:#182538; color:#d7e4f6; }
QToolButton:hover { background:#263c59; border-color:#405776; }
QToolButton:disabled, QPushButton:disabled { color:#6a7a92; background:#182234; border-color:#243248; }
QPushButton { color:#d5e4f7; background:#22334a; border-color:#3a506c; }
QPushButton:hover { background:#304a6a; }
QDockWidget::title { background:#1c2a3f; color:#cfdbed; }
QTreeWidget { background:#121d2e; color:#b9cbe0; }
QTreeWidget::item:selected { background:#264364; color:#eef6ff; }
QDoubleSpinBox, QSpinBox, QComboBox { background:#15243a; color:#e6eefb; border-color:#3a4e68; }
QLineEdit, QListWidget { background:#15243a; color:#e6eefb; border-color:#3a4e68; }
QLineEdit:focus { border-color:#dba24a; }
QListWidget::item:selected { background:#264364; color:#eef6ff; }
QComboBox QAbstractItemView { background:#1d2e45; color:#e4eefb; selection-background-color:#36567a; }
QPlainTextEdit { background:#0e1827; color:#9eb6cf; }
QSplitter::handle { background:#28384e; }
QSplitter::handle:hover { background:#dba24a; }
QScrollArea { border:0; background:#121b2b; }
QLabel#DetailsHeading { background:#1c2c44; color:#c3d5ec; }
QWidget#ViewportTools { background:#17263b; }
QLabel#ResultCard { background:#1b2c43; color:#c5ddf5; border-color:#31475f; }
QWidget#DetailsPanel, QScrollArea#PropertiesScroll { background:#121b2b; }
QScrollBar:vertical { background:#19273b; }
QScrollBar::handle:vertical { background:#425c7e; }
QWidget#ApplicationHeader { background:#0d1420; }
"""

MIDNIGHT_STYLE = """
QMainWindow, QWidget { background:#080b12; color:#dce5f3; }
QMenuBar, QStatusBar, QWidget#ApplicationHeader { background:#03050a; }
QMenu { background:#0d1320; border:1px solid #2c3850; }
QMenu::item:selected { background:#263653; }
QToolTip { background:#131d30; color:#edf3ff; border-color:#506489; }
QTabWidget::pane, QTabBar::tab { background:#0c111c; }
QTabBar::tab:selected { background:#182238; color:#c4d5ff; border-top-color:#91aeed; }
QPushButton, QToolButton { background:#111a2b; border-color:#2c3b55; }
QPushButton:hover, QToolButton:hover { background:#1d2b45; border-color:#4b6591; }
QPushButton:disabled, QToolButton:disabled { background:#0c111c; color:#66738a; border-color:#202a3c; }
QDockWidget::title, QLabel#DetailsHeading { background:#0e1625; color:#c8d7ee; }
QTreeWidget { background:#080d16; }
QTreeWidget::item:selected { background:#203252; color:#eef4ff; }
QDoubleSpinBox, QSpinBox, QComboBox, QLineEdit, QListWidget { background:#0c1422; border-color:#2d3c57; }
QComboBox QAbstractItemView { background:#101a2c; selection-background-color:#2b4065; }
QPlainTextEdit { background:#05080e; color:#a9bbd7; }
QWidget#DetailsPanel, QScrollArea#PropertiesScroll { background:#080b12; }
QWidget#ViewportTools { background:#0b1220; }
QLabel#ResultCard { background:#0e1727; border-color:#283853; color:#d0e2ff; }
QSplitter::handle { background:#202b40; }
QSplitter::handle:hover { background:#91aeed; }
QScrollBar:vertical { background:#0c111c; }
QScrollBar::handle:vertical { background:#35486a; }
QProgressBar { background:#0b1220; border-color:#2d3c57; }
QProgressBar::chunk { background:#91aeed; }
"""
