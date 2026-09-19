"""Read-only code surface with an IDE-style line gutter and Python colors."""

import keyword
import re

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QColor, QFontDatabase, QPainter, QSyntaxHighlighter
from PySide6.QtWidgets import QPlainTextEdit, QWidget


class PythonHighlighter(QSyntaxHighlighter):
    tokens = re.compile(r'''\#[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\b\d+(?:\.\d+)?\b|\b[A-Za-z_]\w*\b''')

    def __init__(self, document):
        super().__init__(document)
        self.enabled = False

    def highlightBlock(self, text):
        if not self.enabled:
            return
        # Keep triple-quoted docstrings colored across text blocks.
        state = self.previousBlockState()
        start = 0
        self.setCurrentBlockState(0)
        spans = []
        if state in (1, 2):
            quote = '"""' if state == 1 else "'''"
            end = text.find(quote)
            if end == -1:
                self.setFormat(0, len(text), QColor('#a8c7a5'))
                self.setCurrentBlockState(state)
                return
            spans.append((0, end + 3))
            start = end + 3
        while start < len(text):
            found = re.search(r'''"""|''' + "'''", text[start:])
            if not found:
                break
            begin = start + found.start()
            quote = found.group()
            end = text.find(quote, begin + 3)
            if end == -1:
                spans.append((begin, len(text)))
                self.setCurrentBlockState(1 if quote == '"""' else 2)
                break
            spans.append((begin, end + 3))
            start = end + 3
        for match in self.tokens.finditer(text):
            value = match.group()
            color = None
            if value.startswith('#'):
                color = '#7f8490'
            elif value.startswith(('"', "'")):
                color = '#a8c7a5'
            elif value in keyword.kwlist:
                color = '#c4b5e8'
            elif value[0].isdigit():
                color = '#e6c48e'
            elif value in ('self', 'True', 'False', 'None'):
                color = '#aecbfa'
            if color:
                self.setFormat(match.start(), len(value), QColor(color))
        for begin, end in spans:
            self.setFormat(begin, end - begin, QColor('#a8c7a5'))


class LineNumbers(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def paintEvent(self, event):
        self.editor.paint_line_numbers(event)


class CodeView(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('codeEditor')
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ') * 4)
        self.gutter = LineNumbers(self)
        self.highlighter = PythonHighlighter(self.document())
        self.blockCountChanged.connect(self.update_gutter_width)
        self.updateRequest.connect(self.update_gutter)
        self.update_gutter_width()

    def update_gutter_width(self, *_):
        width = 22 + self.fontMetrics().horizontalAdvance('9') * len(str(self.blockCount()))
        self.setViewportMargins(width, 0, 0, 0)
        rect = self.contentsRect()
        self.gutter.setGeometry(QRect(rect.left(), rect.top(), width, rect.height()))

    def update_gutter(self, rect, dy):
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_gutter_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_gutter_width()

    def paint_line_numbers(self, event):
        painter = QPainter(self.gutter)
        painter.fillRect(event.rect(), QColor('#1b1c20'))
        painter.setFont(self.font())
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        while block.isValid() and top <= event.rect().bottom():
            height = round(self.blockBoundingRect(block).height())
            if block.isVisible() and top + height >= event.rect().top():
                painter.setPen(QColor('#727783'))
                painter.drawText(0, top, self.gutter.width() - 10, height,
                                 Qt.AlignmentFlag.AlignRight, str(block.blockNumber() + 1))
            top += height
            block = block.next()
