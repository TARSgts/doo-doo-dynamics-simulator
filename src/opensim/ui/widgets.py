"""Reusable controls that do not change numeric inputs when scrolling panels."""
from PySide6.QtCore import QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QScrollArea, QDoubleSpinBox, QSpinBox

def forward_wheel_to_panel(control, event):
    parent = control.parentWidget()
    while parent is not None and not isinstance(parent, QScrollArea):
        parent = parent.parentWidget()
    if parent is None:
        event.ignore()
        return
    viewport = parent.viewport()
    position = QPointF(viewport.mapFromGlobal(event.globalPosition().toPoint()))
    forwarded = QWheelEvent(position, event.globalPosition(), event.pixelDelta(), event.angleDelta(), event.buttons(),
                            event.modifiers(), event.phase(), event.inverted(), event.source(), event.pointingDevice())
    QApplication.sendEvent(viewport, forwarded)
    event.accept()


class ScrollSafeDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event):
        forward_wheel_to_panel(self, event)


class ScrollSafeSpinBox(QSpinBox):
    def wheelEvent(self, event):
        forward_wheel_to_panel(self, event)
