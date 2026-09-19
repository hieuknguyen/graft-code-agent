"""Small, themeable line icons shared by the desktop surfaces."""

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


PATHS = {
    "files": '<path d="M9 3h8l4 4v13H9zM17 3v5h4M5 7H3v14h12"/>',
    "folder": '<path d="M3 6h7l2 2h9v12H3z"/>',
    "chat": '<path d="M4 4h16v12H9l-5 4zM8 8h8M8 12h5"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
    "terminal": '<path d="m4 6 5 5-5 5M12 17h8"/>',
    "settings": '<path d="M4 6h16M4 12h16M4 18h16M8 3v6M16 9v6M10 15v6"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "refresh": '<path d="M20 7v5h-5M4 17v-5h5M5 7a8 8 0 0 1 13-2l2 3M4 16l2 3a8 8 0 0 0 13-2"/>',
    "activity": '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
    "send": '<path d="M12 20V4m-6 6 6-6 6 6"/>',
    "undo": '<path d="M4 4v6h6M4 10l4-4a7 7 0 1 1 1 13"/>',
    "check": '<path d="m4 12 5 5L20 6"/>',
    "close": '<path d="m6 6 12 12M6 18 18 6"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1.5"/><path d="m3 17 6-6 4 4 3-3 5 5"/>',
    "code": '<path d="m8 5-6 7 6 7M16 5l6 7-6 7M14 3l-4 18"/>',
    "changes": '<path d="M8 3v12a4 4 0 0 0 4 4h5M13 5h4v8"/><circle cx="8" cy="3" r="2"/><circle cx="17" cy="19" r="2"/><circle cx="17" cy="13" r="2"/>',
    "spark": '<path d="M12 2 9 9l-7 3 7 3 3 7 3-7 7-3-7-3z"/>',
    "panel": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16"/>',
    "play": '<path d="m8 4 12 8-12 8z"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="1"/>',
}


def icon(name: str, color: str = "#a4a7af", size: int = 18) -> QIcon:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="none" stroke="{color}" stroke-width="1.6" '
        f'stroke-linecap="round" stroke-linejoin="round">{PATHS[name]}</svg>'
    )
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)
