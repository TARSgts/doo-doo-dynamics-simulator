"""Reports for the desktop workbench."""
import json
from PySide6.QtCore import QUrl
from PySide6.QtGui import QTextDocument
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QDialog, QLabel, QMessageBox, QPushButton, QSizePolicy, QVBoxLayout
from opensim.hover_help import BUTTON_HELP
from opensim.ui.resources import REPOSITORY_ROOT


class ReportsMixin:
    def show_validation(self):
        report_path = REPOSITORY_ROOT / "docs" / "cantilever" / "report.json"
        if not report_path.is_file():
            raise ValueError("Run open-sim validate-cantilever --out <new folder> to produce the validation study")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        fine = report["cases"][-1]
        QMessageBox.information(self, "Published reference benchmark",
                                f"1 m × 20 mm × 20 mm beam · 10 N tip force\n\n"
                                f"Euler–Bernoulli: {report['euler_bernoulli_tip_z_m'] * 1000:.6f} mm\n"
                                f"C3D10 tip-section mean: {fine['tip_mean_z_m'] * 1000:.6f} mm\n"
                                f"Error: {fine['tip_error_fraction'] * 100:.4f}%\n"
                                f"Final mesh change: {report['last_mesh_change_fraction'] * 100:.4f}%\n\n"
                                "This reference study is independent of the currently selected project.\n"
                                "See docs/cantilever/REPORT.md for assumptions, criteria and plots.")

    def show_reference_report(self, benchmark):
        titles = {"timoshenko": "Timoshenko beam validation", "hole": "Circular-hole stress validation", "modal": "Modal beam validation", "distributed": "Distributed-load validation", "thermal": "Steady thermal verification"}
        if benchmark not in titles:
            raise ValueError("Unknown reference benchmark")
        if benchmark in self.reference_dialogs:
            dialog = self.reference_dialogs[benchmark]
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
            return dialog
        directory = REPOSITORY_ROOT / "docs" / benchmark
        report = directory / "REPORT.md"
        if not report.is_file():
            raise ValueError("This checkout does not include the reference report")
        document = QTextDocument()
        document.setMarkdown(report.read_text(encoding="utf-8"))
        dark = self.theme != "light"
        background, foreground = ("#080b12" if self.theme == "midnight" else "#121b2b", "#d8e4f1") if dark else ("#ffffff", "#27374a")
        style = ("<style>body{background:" + background + ";color:" + foreground + ";font:14px 'Segoe UI';margin:24px;line-height:1.55}"
                 "img{max-width:100%;height:auto}table{border-collapse:collapse;width:100%;font-size:13px}"
                 "td,th{border:1px solid #50627a;padding:7px}a{color:#65b5ff}pre{white-space:pre-wrap}</style>")
        html = document.toHtml().replace("</head>", style + "</head>")
        dialog = QDialog(self)
        dialog.setWindowTitle(titles[benchmark] + " — Published reference study")
        dialog.setMinimumSize(640, 420)
        dialog.resize(min(1250, self.width()), min(850, self.height()))
        layout = QVBoxLayout(dialog)
        note = QLabel("Published reference benchmark — independent of the currently selected project's settings.")
        note.setObjectName("ReferenceNotice")
        note.setWordWrap(True)
        note.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(note)
        view = QWebEngineView(dialog)
        view.setObjectName("ReferenceContent")
        view.setAccessibleName(titles[benchmark] + " report")
        view.setHtml(html, QUrl.fromLocalFile(str(directory) + "/"))
        layout.addWidget(view, 1)
        close = QPushButton("Back to model")
        close.setToolTip(BUTTON_HELP["Back to model"])
        close.clicked.connect(dialog.close)
        layout.addWidget(close)
        self.reference_dialogs[benchmark] = dialog
        dialog.show()
        return dialog

    def show_convergence_report(self, results=None):
        results = results or self.workspace.get_convergence_results(self.require_project())
        key = ("convergence", results["job_id"])
        url = QUrl.fromLocalFile(results["artifacts"]["report.html"])
        url.setQuery("theme=" + (self.theme or "dark"))
        if key in self.reference_dialogs:
            dialog = self.reference_dialogs[key]
            dialog.findChild(QWebEngineView, "ConvergenceReport").setUrl(url)
            dialog.show()
            dialog.raise_()
            return dialog
        summary = results["summary"]
        dialog = QDialog(self)
        dialog.setWindowTitle("Mesh convergence study")
        dialog.setMinimumSize(640, 420)
        dialog.resize(min(1250, self.width()), min(900, self.height()))
        layout = QVBoxLayout(dialog)
        note = QLabel(f"{len(summary['levels'])} meshes · {summary['levels'][0]['tetrahedra']:,} → {summary['levels'][-1]['tetrahedra']:,} elements · "
                      "Click “open” in the table to inspect any mesh's result.")
        note.setObjectName("ReferenceNotice")
        note.setWordWrap(True)
        layout.addWidget(note)
        view = QWebEngineView(dialog)
        view.setObjectName("ConvergenceReport")
        view.setAccessibleName("Convergence study report")
        view.setUrl(url)
        layout.addWidget(view, 1)
        close = QPushButton("Back to model")
        close.setToolTip(BUTTON_HELP["Back to model"])
        close.clicked.connect(dialog.close)
        layout.addWidget(close)
        self.reference_dialogs[key] = dialog
        dialog.show()
        return dialog
