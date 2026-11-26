"""Две темы оформления для всех окон приложения."""

from PyQt6.QtGui import QColor, QPalette

THEMES = {"light": "Светлая", "dark": "Тёмная"}


def apply_theme(app, theme):
    """Меняем цвета, сохраняя системный размер текста."""
    dark = theme == "dark"
    app.setStyle("Fusion")
    palette = QPalette()
    colors = {
        "Window": "#24262b" if dark else "#f3f4f6",
        "WindowText": "#f2f3f5" if dark else "#202124",
        "Base": "#191b20" if dark else "#ffffff",
        "AlternateBase": "#2d3036" if dark else "#edf0f5",
        "Text": "#f2f3f5" if dark else "#202124",
        "Button": "#343740" if dark else "#e6e9ef",
        "ButtonText": "#f2f3f5" if dark else "#202124",
        "Highlight": "#365fa8" if dark else "#315fa8",
        "HighlightedText": "#ffffff",
        "ToolTipBase": "#343740" if dark else "#ffffff",
        "ToolTipText": "#f2f3f5" if dark else "#202124",
        "Link": "#9dbfff" if dark else "#174ea6",
        "LinkVisited": "#d2b5ff" if dark else "#6a329f",
        "PlaceholderText": "#a6acb7" if dark else "#626975",
        "Light": "#505662" if dark else "#ffffff",
        "Midlight": "#414650" if dark else "#eef0f4",
        "Mid": "#484d58" if dark else "#bcc2cc",
        "Dark": "#111318" if dark else "#8a929f",
        "Shadow": "#08090b" if dark else "#5a616b",
    }
    for role, color in colors.items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(color))
    for role in ["WindowText", "Text", "ButtonText"]:
        palette.setColor(
            QPalette.ColorGroup.Disabled,
            getattr(QPalette.ColorRole, role),
            QColor("#969ba6" if dark else "#747b86"),
        )
    app.setPalette(palette)
    error = "#ffaaa3" if dark else "#b3261e"
    app.setStyleSheet('QLabel[errorMessage="true"] { color: ' + error + "; }")
