from nicegui import ui

from mcsu_gui.theme import GRADE_COLORS, MUTED


def status_badge(text: str = "Idle", color: str = MUTED):
    with ui.row().classes("status-chip items-center no-wrap"):
        dot = ui.element("span").classes("dot")
        dot.style(f"background: {color}")
        label = ui.label(text)
    label._dot = dot
    return label


def paint_badge(badge, text: str, color: str):
    badge.set_text(text)
    dot = getattr(badge, "_dot", None)
    if dot is not None:
        dot.style(replace=f"background: {color}")


class Tile:
    """Glass-style label + value card."""

    def __init__(self, label: str, value: str = "—", color: str = "#e0e0e0"):
        with ui.column().classes("tile w-full"):
            ui.label(label).classes("label mono")
            self._value = ui.label(value).classes("value")
            self._value.style(f"color: {color}")

    def set(self, text: str, color: str = None):
        self._value.set_text(text)
        if color:
            self._value.style(replace=f"color: {color}")


class Panel:
    """Section panel with an optional accent border (used for TOTAL AP)."""

    def __init__(self, title: str, accent: bool = False):
        cls = "panel-accent" if accent else "panel"
        self.el = ui.column().classes(f"{cls} w-full")
        with self.el:
            ui.label(title).classes("panel-title mono")
            self.content = ui.column().classes("w-full gap-2")


class GradeBadge:
    def __init__(self, grade: str, count: int = 0):
        color = GRADE_COLORS.get(grade, "#888")
        with ui.column().classes("mono").style(
            f"border: 2px solid {color}; border-radius: 10px; padding: 4px 10px; "
            "text-align: center; min-width: 52px;"
        ):
            ui.label(grade).style(f"font-size: 15px; font-weight: 700; color: {color}")
            self._count = ui.label(str(count)).classes("mono").style(
                "font-size: 15px; font-weight: 700; color: #fff"
            )

    def set_count(self, count: int):
        self._count.set_text(str(count))