"""Viewport for the desktop workbench."""
import base64
import hashlib
import json
from pathlib import Path
import time
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QLabel, QMessageBox, QVBoxLayout
from opensim.results import refresh_viewer
from opensim.cat_language import cat_text
from opensim.ui.resources import PACKAGE_ROOT


class ViewportMixin:
    def gif_options(self):
        """Ask for GIF size and smoothness. Returns (width or None, frames) or None if cancelled."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Export mode shape GIF")
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        size = QComboBox()
        for text, value in (("Medium · 960 px wide", 960), ("Large · 1280 px wide", 1280), ("Small · 640 px wide", 640),
                            ("Same as the viewport", None)):
            size.addItem(text, value)
        size.setToolTip("Width of the GIF. It is never larger than the viewport, so enlarge the window for a bigger GIF.")
        smoothness = QComboBox()
        for text, value in (("Smooth · 36 frames", 36), ("Very smooth · 48 frames", 48), ("Smaller file · 24 frames", 24)):
            smoothness.addItem(text, value)
        smoothness.setToolTip("Frames per vibration cycle. More frames look smoother but make a bigger file.")
        form.addRow("Size", size)
        form.addRow("Smoothness", smoothness)
        layout.addLayout(form)
        note = QLabel("Uses the current camera, colors and theme. One full vibration cycle that loops forever, slowed to "
                      "about one cycle per second. The shape is normalized, so the motion size is illustrative.")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Choose file…")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if not dialog.exec():
            return None
        return size.currentData(), smoothness.currentData()

    def export_mode_gif(self, path=None, width=960, frames=36):
        if self.gif_export is not None:
            raise ValueError("A GIF export is already running")
        state = self.workspace.ui_state()
        if state["view"] != "modal":
            raise ValueError("Open a modal result first: Solution → Modal, then pick a mode")
        results = self.workspace.get_modal_results(self.require_project())
        mode = state["modal_mode"]
        frequency = results["summary"]["frequencies_Hz"][mode - 1]
        if path is None:
            options = self.gif_options()
            if options is None:
                return
            width, frames = options
            project = self.workspace.get_project(self.project_id)
            safe_name = "".join(character if character.isalnum() or character in "-_" else "-" for character in project["name"]).strip("-") or "model"
            suggested = Path.home() / "Pictures" / f"{safe_name}-mode-{mode}-{frequency:.4g}Hz.gif"
            if not suggested.parent.is_dir():
                suggested = Path.home() / suggested.name
            path, _ = QFileDialog.getSaveFileName(self, "Save mode shape GIF", str(suggested), "Animated GIF (*.gif)")
            if not path:
                return
        path = Path(path)
        if path.suffix.lower() != ".gif":
            path = path.with_suffix(".gif")
        self.gif_export = {"path": path, "started": time.time(), "mode": mode, "waiting": False}
        self.export_gif_button.setEnabled(False)
        self.status_label.setText(f"Exporting mode {mode} GIF…")
        options = json.dumps({"frames": frames, "width": width})
        self.view.page().runJavaScript(
            f"typeof startModeGifExport==='function'?(startModeGifExport({options}).catch(()=>{{}}),true):false", self.gif_export_started)

    def gif_export_started(self, started):
        if self.gif_export is None:
            return
        if not started:
            self.finish_gif_export("This view cannot export a GIF. Open a modal result and try again.")
            return
        self.gif_timer.start()

    def poll_gif_export(self):
        if self.gif_export is None or self.gif_export["waiting"]:
            return
        if time.time() - self.gif_export["started"] > 300:
            self.finish_gif_export("GIF export took longer than 5 minutes and was abandoned. Try a smaller size or fewer frames.")
            return
        self.gif_export["waiting"] = True
        self.view.page().runJavaScript(
            "typeof gifExportState==='object'?JSON.stringify({status:gifExportState.status,progress:gifExportState.progress,"
            "error:gifExportState.error,bytes:gifExportState.bytes}):null", self.gif_export_progress)

    def gif_export_progress(self, text):
        if self.gif_export is None:
            return
        self.gif_export["waiting"] = False
        state = json.loads(text) if text else None
        if not state or state["status"] == "idle":
            self.finish_gif_export("GIF export was interrupted because the view changed. Try again.")
        elif state["status"] == "error":
            self.finish_gif_export("GIF export failed: " + str(state["error"]))
        elif state["status"] == "running":
            self.status_label.setText(f"Exporting mode {self.gif_export['mode']} GIF… {state['progress'] * 100:.0f}%")
        elif state["status"] == "done":
            self.gif_timer.stop()
            self.gif_export["waiting"] = True
            self.view.page().runJavaScript("takeGifExport()", self.save_gif_export)

    def save_gif_export(self, data):
        if self.gif_export is None:
            return
        try:
            content = base64.b64decode(data or "", validate=True)
            if not content.startswith(b"GIF89a"):
                raise ValueError("the viewer returned no GIF data")
            path = self.gif_export["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        except (OSError, ValueError) as error:
            self.finish_gif_export(f"Could not save the GIF: {error}")
            return
        self.finish_gif_export(None, f"Saved GIF ({len(content) / 1e6:.1f} MB): {path}")

    def finish_gif_export(self, error=None, message=None):
        self.gif_timer.stop()
        self.gif_export = None
        self.export_gif_button.setEnabled(True)
        self.status_label.setText(error or message)
        if error:
            QMessageBox.warning(self, "Export GIF", error)

    def show_stress(self):
        result = self.workspace.get_results(self.require_project())
        if "maximum_von_mises_Pa" not in result["summary"]:
            raise ValueError("Solve again to generate recovered stress contours")
        self.workspace.show_project(self.project_id, "results")
        self.result_component.setCurrentIndex(4)
        self.refresh()

    def select_mode(self, *args):
        if self.modal_selector.currentData() is not None and self.project_id:
            self.workspace.show_project(self.project_id, "modal", self.modal_selector.currentData())
            self.refresh()

    def change_view(self, view):
        self.workspace.show_project(self.require_project(), view)

    def apply_view_options(self, *args):
        state = self.workspace.ui_state()
        mode = state["view"]
        if mode == "thermal" or mode in {'cfd','cfd_slice'}:
            mode = "results"
        animation_label = "Pause mode" if self.animate_mode.isChecked() else "Animate mode"
        self.animate_mode.setText(cat_text(animation_label) if self.language == "cat" else animation_label)
        scale = ["auto", 1, 10, 100, 500][self.deformation.currentIndex()]
        if state['study']=='cfd':scale=0
        if mode == "modal":
            scale = "auto"
        component = ["magnitude", "x", "y", "z", "stress"][self.result_component.currentIndex()]
        self.view.page().runJavaScript(
            f"if(typeof setViewportMode==='function'){{setViewportMode({json.dumps(mode)});setDeformationScale({json.dumps(scale)});}}"
            f"if(typeof setTheme==='function')setTheme({json.dumps(self.theme)});"
            f"if(typeof setThermalStudyMode==='function')setThermalStudyMode({json.dumps(state['study'] == 'thermal')});"
            f"if(typeof setCatMode==='function')setCatMode({json.dumps(self.workspace.ui_state()['language'] == 'cat')});"
            f"if(typeof setModeAnimation==='function')setModeAnimation({json.dumps(mode == 'modal' and self.animate_mode.isChecked())});"
            f"if(typeof setModalAmplitude==='function')setModalAmplitude({json.dumps(self.modal_amplitude.currentData())});"
            f"if(typeof setResultComponent==='function')setResultComponent({json.dumps(component)});")
        self.apply_flow_preview()

    def apply_flow_preview(self):
        settings=None
        if self.project_id and self.workspace.ui_state()['study']=='cfd':
            p=self.workspace.get_project(self.project_id)['parameters']
            settings={key:p[key] for key in ('cfd_inlet_region','cfd_outlet_region')}
            settings.update({key:self.selectors[key].currentData() for key in ('cfd_backend','cfd_flow_axis')})
            settings.update({key:self.fields[key].value() for key in ('cfd_speed_m_s','cfd_pressure_drop_Pa')})
        self.view.page().runJavaScript(f"if(typeof setFlowPreview==='function')setFlowPreview({json.dumps(settings)});")

    def apply_camera(self, *args):
        if self.camera.currentIndex()==4:
            self.view.page().runJavaScript("if(typeof homeViewport==='function')homeViewport();")
            return
        orientation = ["isometric", "front", "top", "flipped-front"][self.camera.currentIndex()]
        self.view.page().runJavaScript(f"if(typeof setViewOrientation==='function')setViewOrientation({json.dumps(orientation)});")

    def viewer_for_artifact(self, artifact):
        sources = [artifact, (PACKAGE_ROOT / "viewer.html"), (PACKAGE_ROOT / "viewport.js")]
        identity = "|".join(str(path.resolve()) + ":" + str(path.stat().st_mtime_ns) for path in sources)
        target = self.workspace.root / ".viewer-cache" / (hashlib.sha256(identity.encode()).hexdigest() + ".html")
        if not target.is_file():
            refresh_viewer(artifact, target)
        return target
