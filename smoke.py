"""画面を出さずに組み立てだけ検証する。開発用。"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import main as app_main
import theme

app = QApplication(sys.argv)
target = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
win = app_main.MainWindow(target)

print("theme      :", win._theme, "/ available:", list(theme.PALETTES))
print("path       :", win._path)
print("rows       :", win.model.rowCount())
print("address    :", win.address.text())
print("status     :", win.status.text())
print("sidebar    :", win.sidebar.count(), "items")
print("first rows :")
for r in range(min(6, win.model.rowCount())):
    e = win.model.entry(r)
    print("   ", "D" if e.is_dir else "f", e.name)

win.model.set_filter("py")
print("filter 'py':", win.model.rowCount())
win.model.set_filter("")
win._on_header(1)
print("sort size  :", [win.model.entry(r).name for r in range(min(4, win.model.rowCount()))])

for name in theme.PALETTES:
    win._set_theme(name)
print("all themes applied ok")
