"""Presentation for the desktop workbench."""
from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QComboBox, QDockWidget, QLabel, QPushButton, QToolButton
from opensim.cat_language import cat_text
from opensim.ui.styles import DARK_STYLE, MIDNIGHT_STYLE, STYLE


class PresentationMixin:
    def set_theme(self, theme):
        self.workspace.set_theme(theme)
        self.apply_theme()
        self.apply_language()

    def set_language(self, language):
        self.workspace.set_language(language)
        self.apply_language()
        self.apply_view_options()

    def present_text(self, identity, current, setter):
        source, rendered = self.presentation_text.get(identity, (current, None))
        if current != rendered:
            source = current
        target = cat_text(source) if self.language == "cat" else source
        if current != target:
            setter(target)
        self.presentation_text[identity] = source, target

    def apply_language(self):
        previous = self.language
        self.language = self.workspace.ui_state()["language"]
        active = self.language == "cat"
        blocker = QSignalBlocker(self.cat_action)
        self.cat_action.setChecked(active)
        del blocker
        skipped = {self.viewport_title, self.status_label, self.progress_label}
        for widget in self.findChildren(QLabel) + self.findChildren(QPushButton) + self.findChildren(QToolButton):
            if widget not in skipped:
                self.present_text((widget, "text"), widget.text(), widget.setText)
        for action in self.findChildren(QAction):
            if action is not self.cat_action:
                self.present_text((action, "text"), action.text(), action.setText)
        for dock in self.findChildren(QDockWidget):
            self.present_text((dock, "title"), dock.windowTitle(), dock.setWindowTitle)
        self.present_text((self, "title"), self.windowTitle(), self.setWindowTitle)
        for index in range(self.ribbon.count()):
            self.present_text((self.ribbon, index), self.ribbon.tabText(index), lambda value, tab=index: self.ribbon.setTabText(tab, value))
        for combo in self.findChildren(QComboBox):
            blocker = QSignalBlocker(combo)
            for index in range(combo.count()):
                self.present_text((combo, index), combo.itemText(index), lambda value, item=index, control=combo: control.setItemText(item, value))
            del blocker
        def translate_children(parent, path):
            for index in range(parent.childCount()):
                child = parent.child(index)
                identity = (self.tree, "study", *path, index)
                self.present_text(identity, child.text(0), lambda value, item=child: item.setText(0, value))
                translate_children(child, (*path, index))
        for index in range(self.tree.topLevelItemCount()):
            root = self.tree.topLevelItem(index)
            translate_children(root, (root.data(0, Qt.ItemDataRole.UserRole)[0],))
        self.update_ribbon_height()
        if previous != self.language:
            self.apply_view_options()

    def apply_theme(self):
        self.theme = self.workspace.ui_state()["theme"]
        self.setStyleSheet(STYLE + (DARK_STYLE if self.theme != "light" else "") + (MIDNIGHT_STYLE if self.theme == "midnight" else ""))
        for theme, action in self.theme_actions.items():
            blocker = QSignalBlocker(action)
            action.setChecked(self.theme == theme)
            del blocker
        self.legend.setStyleSheet("padding:9px;color:" + ("#a9bbd7;background:#0b1220" if self.theme == "midnight" else "#9fb9d7;background:#132238" if self.theme == "dark" else "#55697e;background:#fff"))
        self.apply_view_options()
