from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout,
                               QLabel, QMessageBox, QPushButton, QSpinBox, QVBoxLayout)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT

from opensim.plots import (COMPONENTS, PLOT_NAMES, available_plots, make_figure, make_plot_data,
                           plot_provenance, write_plot_csv)
from opensim.project_dialogs import open_folder


class PlotDialog(QDialog):
    def __init__(self, workspace, source, dark=False, parent=None):
        super().__init__(parent)
        self.workspace, self.source = workspace, source
        self.export_directory = source.directory / "plots"
        self.setWindowTitle("Result plots — " + source.project_name)
        self.resize(1100, 760)
        self.setMinimumSize(680, 500)
        layout = QVBoxLayout(self)
        self.banner = QLabel()
        self.banner.setWordWrap(True)
        layout.addWidget(self.banner)
        row = QHBoxLayout()
        self.plot_type = QComboBox()
        self.plot_type.setToolTip("Choose a plot from the completed results for this study.")
        for key in available_plots(source):
            self.plot_type.addItem(PLOT_NAMES[key], key)
        layout.addWidget(self.plot_type)
        self.axis = QComboBox()
        self.axis.addItems(["X position", "Y position", "Z position"])
        self.axis.setToolTip("Choose the undeformed coordinate for the horizontal axis. Scatter includes nodes across the whole model.")
        row.addWidget(self.axis)
        self.component = QComboBox()
        for key, title in COMPONENTS.items():
            self.component.addItem(title, key)
        self.component.setToolTip("Choose total magnitude or a signed X/Y/Z component.")
        row.addWidget(self.component)
        self.mode = QComboBox()
        self.mode.setToolTip("Choose the saved, normalized vibration mode to plot.")
        if source.study == "modal":
            for index, frequency in enumerate(source.arrays["frequencies_Hz"], 1):
                self.mode.addItem(f"Mode {index} · {frequency:.6g} Hz", index)
            self.mode.setCurrentIndex(max(0, self.mode.findData(workspace.ui_state()["modal_mode"])))
        row.addWidget(self.mode)
        self.bins = QSpinBox()
        self.bins.setRange(5, 200)
        self.bins.setValue(30)
        self.bins.setPrefix("Bins: ")
        self.bins.setToolTip("Number of intervals in a nodal-value histogram. CSV contains each interval's edges and node count.")
        row.addWidget(self.bins)
        layout.addLayout(row)
        self.dark_plot = QCheckBox("Dark plot")
        self.dark_plot.setChecked(dark)
        self.dark_plot.setToolTip("Use a dark chart background. Turn off for white-background figures. Export follows the displayed chart theme.")
        layout.addWidget(self.dark_plot)
        self.figure = make_figure(source, make_plot_data(source, self.plot_type.currentData()), dark)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        # Use the explicit save controls below so formats and output locations are clear.
        for action in self.toolbar.actions():
            if action.text().lower() == "save":
                action.setVisible(False)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas, 1)
        self.status = QLabel("Pan and zoom with the chart toolbar. Export the figure or the values used to draw it.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        actions = QHBoxLayout()
        for title, tooltip, callback in (
            ("Save figure…", "Save the displayed chart, including its current zoom, as PNG or SVG.", self.save_figure),
            ("Export CSV…", "Save the plotted values and a metadata file identifying the project, run and units.", self.export_csv),
            ("Open plot folder", "Open the most recent export folder, or this run's plot folder.", self.open_exports),
            ("Close", "Close plots and return to the study.", self.close)):
            button = QPushButton(title)
            button.setToolTip(tooltip)
            button.clicked.connect(lambda checked=False, action=callback: self.safe(action))
            actions.addWidget(button)
        layout.addLayout(actions)
        for control in (self.plot_type, self.axis, self.component, self.mode):
            control.currentIndexChanged.connect(self.redraw)
        self.bins.valueChanged.connect(self.redraw)
        self.dark_plot.toggled.connect(self.redraw)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_banner)
        self.timer.start(1000)
        self.redraw()

    def safe(self, action):
        try:
            action()
        except Exception as error:
            QMessageBox.warning(self, "Result plots", str(error))

    def redraw(self):
        key = self.plot_type.currentData()
        self.axis.setVisible(key.endswith("position"))
        self.component.setVisible(key.startswith("displacement") or key == "mode-position")
        self.mode.setVisible(key == "mode-position")
        self.bins.setVisible(key.endswith("distribution"))
        self.data = make_plot_data(self.source, key, "xyz"[self.axis.currentIndex()], self.component.currentData(),
                                   self.mode.currentData() or 1, self.bins.value())
        make_figure(self.source, self.data, self.dark_plot.isChecked(), figure=self.figure)
        self.toolbar.update()
        self.canvas.draw_idle()
        self.update_banner()

    def update_banner(self):
        current = self.workspace.get_project(self.source.project_id)
        label = "Saved result for current inputs" if current["revision"] == self.source.revision else "Historical result — project inputs have changed"
        self.banner.setText(f"{label} · {self.source.study.title()} · run {self.source.job_id[:8]} · input revision {self.source.revision}")
        self.banner.setToolTip(str(self.source.directory))

    def default_path(self, suffix):
        self.export_directory.mkdir(parents=True, exist_ok=True)
        key = self.plot_type.currentData()
        if key.endswith("position"):
            key += "-" + "xyz"[self.axis.currentIndex()]
        if key.startswith("displacement") or key.startswith("mode-"):
            key += "-" + self.component.currentData()
        if key.startswith("mode-"):
            key += f"-mode{self.mode.currentData()}"
        if "distribution" in key:
            key += f"-bins{self.bins.value()}"
        return self.export_directory / f"{key}-{self.source.job_id[:8]}{suffix}"

    def save_figure(self):
        filename, selected = QFileDialog.getSaveFileName(self, "Save result figure", str(self.default_path(".png")),
                                                       "PNG image (*.png);;SVG figure (*.svg)")
        if not filename:
            return
        path = Path(filename)
        if path.suffix.lower() not in {".png", ".svg"}:
            path = path.with_suffix(".svg" if selected.startswith("SVG") else ".png")
        import json
        self.figure.savefig(path, dpi=180, metadata={"Title": self.data.title, "Description": json.dumps(plot_provenance(self.source, self.data)), "Creator": "Doo Doo Dynamics Simulator"})
        self.saved(path)

    def export_csv(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Export plotted data", str(self.default_path(".csv")), "CSV data (*.csv)")
        if not filename:
            return
        path = Path(filename)
        if path.suffix.lower() != ".csv":
            path = path.with_suffix(".csv")
        path, metadata = write_plot_csv(path, self.source, self.data)
        self.saved(path, " and " + metadata.name)

    def saved(self, path, extra=""):
        self.export_directory = path.parent
        self.status.setText("Saved " + path.name + extra)
        self.status.setToolTip(str(path.parent))

    def open_exports(self):
        self.export_directory.mkdir(parents=True, exist_ok=True)
        open_folder(self.export_directory)

    def closeEvent(self, event):
        self.timer.stop()
        super().closeEvent(event)

    def showEvent(self, event):
        self.timer.start(1000)
        self.update_banner()
        super().showEvent(event)
