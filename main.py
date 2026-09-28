"""ウィンドウの組み立てと画面遷移。

第一段階として読み取り専用。ファイルを一切変更しない。
構造は Windows 2000 の五層（ツールバー / パンくず / サイドバー / 一覧 / ステータス）。
"""

import ctypes
import os
import shutil
import sys
import uuid

from PySide6.QtCore import QByteArray, QEvent, QPoint, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QKeySequence, QPainter, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QSplitter,
    QStackedWidget,
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

import actions as fileops
import appicon
import control
import model as core
import osops
import session
import theme
import view as ui
import winframe


def _volume_label(drive: str) -> str:
    """ドライブのボリュームラベルを返す。取れなければ空文字。"""
    try:
        buf = ctypes.create_unicode_buffer(256)
        ctypes.windll.kernel32.GetVolumeInformationW(
            drive, buf, len(buf), None, None, None, None, 0
        )
        return buf.value
    except Exception:
        return ""


def _drive_type(drive: str) -> int:
    """GetDriveType の戻り値。2=リムーバブル 3=固定 4=ネットワーク 5=光学。"""
    try:
        return ctypes.windll.kernel32.GetDriveTypeW(drive)
    except Exception:
        return 3


def places():
    """サイドバーに出す行。(見出しか, 表示名, パス) で返す。"""
    home = os.path.expanduser("~")
    rows = [(True, "場所", None)]
    for label, sub in (
        ("デスクトップ", "Desktop"),
        ("ドキュメント", "Documents"),
        ("ダウンロード", "Downloads"),
        ("ホーム", ""),
    ):
        path = os.path.join(home, sub) if sub else home
        if os.path.isdir(path):
            rows.append((False, label, path))

    drives = []
    try:
        drives = list(os.listdrives())
    except (AttributeError, OSError):
        drives = [f"{c}:\\" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                  if os.path.exists(f"{c}:\\")]

    fixed, removable = [], []
    for d in drives:
        (removable if _drive_type(d) == 2 else fixed).append(d)

    if fixed:
        rows.append((True, "ドライブ", None))
        for d in fixed:
            rows.append((False, d.rstrip("\\") or d, d))

    if removable:
        rows.append((True, "リムーバブル", None))
        for d in removable:
            lbl = _volume_label(d)
            letter = d.rstrip("\\") or d
            display = f"{lbl}  ({letter})" if lbl else letter
            rows.append((False, display, d))

    return rows


_DRIVE_INFO = Qt.ItemDataRole.UserRole + 1   # disk_info dict を格納するロール


def _fmt_compact(n: int) -> str:
    """バイト数を GiB 換算で短縮表示する。"""
    if n < 0:
        return "?"
    v = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if v < 1024 or unit == "TB":
            return f"{v:.0f} {unit}" if (v >= 10 or unit in ("B", "KB")) else f"{v:.1f} {unit}"
        v /= 1024
    return "?"


class SidebarDelegate(QStyledItemDelegate):
    """ドライブ行だけ 2 行コンパクト表示する。それ以外は Qt 標準に委ねる。"""

    BAR_W, BAR_H = 42, 3

    def sizeHint(self, option, index):
        if index.data(_DRIVE_INFO) is not None:
            return QSize(option.rect.width(), 30)
        return super().sizeHint(option, index)

    def paint(self, painter: QPainter, option, index):
        info = index.data(_DRIVE_INFO)
        if info is None:
            super().paint(painter, option, index)
            return

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        w = option.widget
        style = w.style() if w else QApplication.style()
        style.drawPrimitive(
            QStyle.PrimitiveElement.PE_PanelItemViewItem, opt, painter, w
        )

        painter.save()
        r = option.rect
        pad = 5
        icon_sz = 14

        pal = option.palette
        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        main_clr = pal.highlightedText().color() if selected else pal.text().color()
        dim_clr = QColor(main_clr)
        dim_clr.setAlphaF(0.58)

        # アイコンを縦中央に置く
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        if icon:
            iy = r.y() + (r.height() - icon_sz) // 2
            icon.paint(painter, QRect(r.x() + pad, iy, icon_sz, icon_sz))

        tx = r.x() + pad + icon_sz + 4
        tw = r.right() - tx - 3

        # 1行目：ドライブ名
        painter.setPen(main_clr)
        painter.setFont(option.font)
        painter.drawText(
            QRect(tx, r.y() + 2, tw, 13),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            index.data(Qt.ItemDataRole.DisplayRole) or "",
        )

        # 2行目：バーとテキストを同じ行に並べる
        y2 = r.y() + 17
        free = info.get("free", -1)
        total = info.get("total", -1)
        text_x = tx
        cap_text = ""

        if total > 0 and free >= 0:
            ratio = max(0.0, min(1.0, (total - free) / total))
            track = QColor(main_clr)
            track.setAlphaF(0.15)
            painter.fillRect(QRect(tx, y2 + 3, self.BAR_W, self.BAR_H), track)
            fill_w = max(1, round(self.BAR_W * ratio))
            bar_clr = (
                QColor("#D94F4F") if ratio > 0.9 else
                QColor("#D99B44") if ratio > 0.75 else
                QColor("#4A9A66")
            )
            painter.fillRect(QRect(tx, y2 + 3, fill_w, self.BAR_H), bar_clr)
            text_x = tx + self.BAR_W + 4
            cap_text = f"{_fmt_compact(free)}/{_fmt_compact(total)}"

        bus = info.get("bus", "")
        device = info.get("device", "")
        parts = [p for p in [cap_text, bus, device] if p]
        line2 = " · ".join(parts)

        small = QFont(option.font)
        small.setPointSizeF(max(6.5, option.font.pointSizeF() * 0.78))
        painter.setFont(small)
        painter.setPen(dim_clr)
        painter.drawText(
            QRect(text_x, y2, r.right() - text_x - 2, 12),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            line2,
        )
        painter.restore()


# 開いている窓を保持する。参照を捨てると Python に回収されて窓が消える。
WINDOWS = []

# 窓から窓へ移動中のタブの控え。ドラッグの間だけここに置く。
PENDING_TABS = {}


# 散らかり度に応じたアイコンの控え。毎回描き直すと無駄なので覚えておく。
_CHAOS_ICONS = {}


def chaos_level():
    """開いているタブと窓の数から、書類の散らかり具合を割り出す。

    実用性はまったく無い。仕事が散らかるほどアイコンもくたびれる。
    """
    tabs = sum(len(w._tabs) for w in WINDOWS)
    windows = len(WINDOWS)
    level = (tabs - 1) * 0.25 + (windows - 1) * 0.5
    level = min(4.0, max(0.0, level))
    # 決まった段にはめる。1.0 は使わず、0.5 の次は 2.0 まで飛ぶ。
    return min(appicon.CRUMPLE_STEPS, key=lambda s: abs(s - level))


_TRAY = None


def _ensure_tray(ico, level):
    """トレイにも同じ顔を出す。散らかり具合を常時さらすための装置。"""
    global _TRAY
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return
    if _TRAY is None:
        _TRAY = QSystemTrayIcon()
        menu = QMenu()
        menu.addAction("新しいウィンドウ", lambda: open_window(os.path.expanduser("~")))
        menu.addSeparator()
        menu.addAction("終了", QApplication.quit)
        _TRAY.setContextMenu(menu)
        _TRAY._menu = menu   # 参照を保持しないとメニューが消える
        _TRAY.activated.connect(_on_tray)
        _TRAY.show()
    _TRAY.setIcon(ico)
    tabs = sum(len(w._tabs) for w in WINDOWS)
    _TRAY.setToolTip(
        f"Filer — 窓 {len(WINDOWS)} / タブ {tabs} / 散らかり度 {level}"
    )


def _on_tray(reason):
    if reason == QSystemTrayIcon.ActivationReason.Trigger and WINDOWS:
        w = WINDOWS[-1]
        w.showNormal()
        w.raise_()
        w.activateWindow()


def refresh_chaos():
    level = chaos_level()
    ico = _CHAOS_ICONS.get(level)
    if ico is None:
        ico = appicon.icon(level)
        _CHAOS_ICONS[level] = ico
    for w in WINDOWS:
        w.setWindowIcon(ico)
    _ensure_tray(ico, level)


def open_window(path, at=None):
    """新しい窓を開く。at を渡すとその位置に出す。"""
    win = MainWindow(path)
    WINDOWS.append(win)
    if at is not None:
        win.move(at)
    win.show()
    win.raise_()
    win.activateWindow()
    refresh_chaos()
    return win


def _segment(buttons):
    """ボタンを隙間なく並べて、ひと繋がりの部品に見せる。"""
    box = QWidget()
    lay = QHBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    for b in buttons:
        lay.addWidget(b)
    return box


class MainWindow(QMainWindow):
    def __init__(self, start):
        super().__init__()
        self.setWindowTitle("Filer")
        self.resize(940, 580)

        self._theme = theme.detect_theme()
        self._history = []
        self._future = []
        self._path = None
        self._show_hidden = False
        self._view_mode = "list"
        # タブごとに現在地と履歴を持つ。表示モードと絞り込みはウィンドウ共通。
        self._tabs = []          # [{path, history, future}]
        self._closed = []        # 閉じたタブの控え（Ctrl+Shift+T 用）
        self._switching = False  # タブ切り替え中は履歴に積まない

        self._build_actions()
        self._build_body()
        self._apply_theme()
        self._setup_frame()
        self.new_tab(start, switch=True)
        self.navigate(start, record=False)

        # マウスのサイドボタンは、どの子ウィジェットの上で押されても拾いたい。
        # ウィンドウ単位だと一覧やサイドバーに吸われるので、アプリ全体で見張る。
        QApplication.instance().installEventFilter(self)

    # --- 枠の自前描画 -------------------------------------------------------
    def _setup_frame(self):
        """枠なしにする。失敗したら通常の枠のまま動かす（Linux や非対応環境）。"""
        self._frameless = False
        if not winframe.IS_WINDOWS:
            return
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.show()          # winId を確定させるために一度出す
        self._frameless = winframe.apply(self)
        if not self._frameless:
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, False)

    def nativeEvent(self, event_type, message):
        if self._frameless and event_type == b"windows_generic_MSG":
            handled, result = winframe.handle(self, message)
            if handled:
                return True, result
        if event_type == b"windows_generic_MSG":
            try:
                import ctypes.wintypes
                msg = ctypes.wintypes.MSG.from_address(int(message))
                # WM_DEVICECHANGE(0x219): DBT_DEVICEARRIVAL(0x8000) / DBT_DEVICEREMOVECOMPLETE(0x8004)
                if msg.message == 0x0219 and msg.wParam in (0x8000, 0x8004):
                    QTimer.singleShot(400, self._fill_sidebar)
            except Exception:
                pass
        return super().nativeEvent(event_type, message)

    def caption_hit(self, gx, gy):
        """掴んで動かせる場所かを答える。ボタンやタブの上では False。"""
        local = self.titlebar.mapFromGlobal(QPoint(gx, gy))
        if not self.titlebar.rect().contains(local):
            return False
        child = self.titlebar.childAt(local)
        if child is None:
            return True
        if child is self.tabbar:
            # タブの無い余白は掴める（Chrome と同じ）
            return self.tabbar.tabAt(self.tabbar.mapFromGlobal(QPoint(gx, gy))) < 0
        return False

    def _toggle_maximized(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        self.btn_max.setText("❐" if self.isMaximized() else "□")

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            button = event.button()
            if button == Qt.MouseButton.BackButton:
                self.go_back()
                return True
            if button == Qt.MouseButton.ForwardButton:
                self.go_forward()
                return True
        return super().eventFilter(obj, event)

    # --- 組み立て -----------------------------------------------------------
    def _build_actions(self):
        """メニューバーは置かない。ショートカットはウィンドウに直接登録する。

        めったに使わないもの（テーマ等）は、ツールバーの右クリックから出す。
        画面を占有せずに行き先だけ残しておく。
        """
        self._menu_actions = []

        # キー割り当ては Chrome に合わせる。Explorer ではなくブラウザの指が基準。
        def make(label, slot, seq=None, checkable=False):
            a = QAction(label, self, checkable=checkable)
            if seq:
                keys = (seq,) if isinstance(seq, str) else seq
                a.setShortcuts([QKeySequence(k) for k in keys])
            a.triggered.connect(slot)
            self.addAction(a)
            return a

        self.act_back = make("戻る", self.go_back, "Alt+Left")
        self.act_fwd = make("進む", self.go_forward, "Alt+Right")
        self.act_up = make("上へ", self.go_up, "Alt+Up")
        make("アドレスバーへ", self._focus_address, ("Ctrl+E", "Alt+D", "F6"))
        make("絞り込みへ", self._focus_search, "Ctrl+F")
        # Ctrl+1〜9 はタブ切り替え用に空けてある。Chrome が使っていない Ctrl+Shift+数字を表示モードに使う。
        make("一覧表示", lambda: self._set_view_mode("list"), "Ctrl+Shift+1")
        make("アイコン表示", lambda: self._set_view_mode("icons"), "Ctrl+Shift+2")

        # タブ。Chrome と同じ並びにする。
        make("新しいウィンドウ", self.new_window, "Ctrl+N")
        make("新しいタブ", lambda: self.new_tab(self._path), "Ctrl+T")
        make("タブを閉じる", self.close_current_tab, "Ctrl+W")
        make("ウィンドウを閉じる", self.close, ("Ctrl+Shift+W", "Alt+F4"))
        make("閉じたタブを開く", self.reopen_tab, "Ctrl+Shift+T")
        make("次のタブ", lambda: self._step_tab(1), "Ctrl+Tab")
        make("前のタブ", lambda: self._step_tab(-1), "Ctrl+Shift+Tab")
        for n in range(1, 9):
            make(f"タブ {n}", lambda _=None, i=n - 1: self._select_tab(i), f"Ctrl+{n}")
        make("最後のタブ", lambda: self._select_tab(len(self._tabs) - 1), "Ctrl+9")

        make("名前の変更", self.rename_selected, "F2")
        make("コピー", self.copy_selected, "Ctrl+C")
        make("切り取り", self.cut_selected, "Ctrl+X")
        make("貼り付け", self.paste_here, "Ctrl+V")
        make("削除", self.delete_selected, "Delete")
        make("プロパティ", self.properties_selected, "Alt+Return")

        act_refresh = make("最新の情報に更新", self.reload, ("F5", "Ctrl+R"))
        self.act_hidden = make("隠しファイルを表示", self._toggle_hidden, "Ctrl+H", checkable=True)
        self._menu_actions += [act_refresh, self.act_hidden]

        sep = QAction(self)
        sep.setSeparator(True)
        self._menu_actions.append(sep)

        group = QActionGroup(self)
        self._theme_actions = {}
        for name in theme.PALETTES:
            a = QAction(f"テーマ: {name}", self, checkable=True)
            a.setChecked(name == self._theme)
            a.triggered.connect(lambda _, n=name: self._set_theme(n))
            group.addAction(a)
            self._theme_actions[name] = a
            self._menu_actions.append(a)

        sep = QAction(self)
        sep.setSeparator(True)
        self._menu_actions.append(sep)
        # 窓とタブをそのままにして立ち上げ直す。exe を作り直した後の乗り換え用。
        self._menu_actions.append(make("再起動（窓とタブはそのまま）", restart_self, "Ctrl+Shift+F5"))

    def _build_body(self):
        root = QWidget(objectName="Root")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # タイトルバー。Chrome と同じくタブを枠の高さに載せて、一段ぶん節約する。
        self.titlebar = ui.DropTitleBar()
        self.titlebar.adopt_tab = self._adopt_tab
        title_row = QHBoxLayout(self.titlebar)
        title_row.setContentsMargins(4, 0, 0, 0)
        title_row.setSpacing(0)

        self.tabbar = ui.TabBar()
        self.tabbar.currentChanged.connect(self._on_tab_changed)
        self.tabbar.tabCloseRequested.connect(self.close_tab)
        # 窓をまたぐ移動の差し込み口
        self.tabbar.take_tab = self._take_tab
        self.tabbar.adopt_tab = self._adopt_tab
        self.tabbar.spawn_window = self._spawn_window
        title_row.addWidget(self.tabbar)

        self.btn_newtab = QToolButton(text="＋", objectName="NewTab")
        self.btn_newtab.setFixedSize(28, 24)
        self.btn_newtab.setToolTip("新しいタブ (Ctrl+T)")
        self.btn_newtab.clicked.connect(lambda: self.new_tab(self._path))
        title_row.addWidget(self.btn_newtab)

        title_row.addStretch(1)  # ここが掴んで動かせる余白になる

        self.btn_min = QToolButton(text="─", objectName="WinMin")
        self.btn_min.clicked.connect(self.showMinimized)
        self.btn_max = QToolButton(text="□", objectName="WinMax")
        self.btn_max.clicked.connect(self._toggle_maximized)
        self.btn_close = QToolButton(text="✕", objectName="WinClose")
        self.btn_close.clicked.connect(self.close)
        for b in (self.btn_min, self.btn_max, self.btn_close):
            b.setFixedSize(44, 30)
            title_row.addWidget(b)

        outer.addWidget(self.titlebar)

        # ツールバー
        tb = QWidget(objectName="Toolbar")
        row = QHBoxLayout(tb)
        row.setContentsMargins(8, 5, 8, 5)
        row.setSpacing(6)
        # 戻る/進むは連結したひと組に見せる（間に隙間を作らない）
        # 戻る/進むは Mac OS X 風に大きめの山括弧で、ひと組に連結する
        self.btn_back = QToolButton(text="‹", objectName="NavL")
        self.btn_back.clicked.connect(self.go_back)
        self.btn_fwd = QToolButton(text="›", objectName="NavR")
        self.btn_fwd.clicked.connect(self.go_forward)
        row.addWidget(_segment([self.btn_back, self.btn_fwd]))

        self.btn_up = QToolButton(text="↑", objectName="Solo")
        self.btn_up.clicked.connect(self.go_up)
        row.addWidget(self.btn_up)

        # 表示切り替え。押しっぱなしで今の表示がわかるようにする。
        self.btn_list = QToolButton(text="☰", objectName="SegL", checkable=True)
        self.btn_list.setChecked(True)
        self.btn_list.clicked.connect(lambda: self._set_view_mode("list"))
        self.btn_icons = QToolButton(text="∷", objectName="SegR", checkable=True)
        self.btn_icons.clicked.connect(lambda: self._set_view_mode("icons"))
        row.addWidget(_segment([self.btn_list, self.btn_icons]))

        for b, tip, size in (
            (self.btn_back, "戻る (Alt+←)", (40, 28)),
            (self.btn_fwd, "進む (Alt+→)", (40, 28)),
            (self.btn_up, "上へ (Alt+↑)", (34, 28)),
            (self.btn_list, "一覧表示 (Ctrl+Shift+1)", (34, 28)),
            (self.btn_icons, "アイコン表示 (Ctrl+Shift+2)", (34, 28)),
        ):
            b.setFixedSize(*size)
            b.setToolTip(tip)

        # アドレスバーはナビゲーションと検索の間で伸ばす
        self.address = QLineEdit(objectName="Address")
        self.address.returnPressed.connect(self._commit_path)
        row.addWidget(self.address, 1)

        self.search = QLineEdit(placeholderText="絞り込む", objectName="Search")
        self.search.setFixedWidth(170)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._on_filter)
        row.addWidget(self.search)
        # 隠れた入口。ツールバーの余白を右クリックすると出る。
        tb.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        tb.addActions(self._menu_actions)
        outer.addWidget(tb)

        # モデルはサイドバーより先に作る（アイコンを引くのに使うため）
        self.model = ui.FileTableModel(self._theme, self)

        # 本体（サイドバー＋一覧）
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setHandleWidth(1)
        split.setChildrenCollapsible(False)

        self.sidebar = QListWidget(objectName="Sidebar")
        self.sidebar.setMinimumWidth(120)
        self.sidebar.setIconSize(QSize(theme.SIDEBAR_ICON, theme.SIDEBAR_ICON))
        self.sidebar.setSpacing(0)
        self.sidebar.setUniformItemSizes(False)
        self.sidebar.itemActivated.connect(self._on_place)
        self.sidebar.itemClicked.connect(self._on_place)
        self.sidebar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.sidebar.customContextMenuRequested.connect(self._sidebar_ctx_menu)
        self.sidebar.setItemDelegate(SidebarDelegate(self.sidebar))
        self._fill_sidebar()
        split.addWidget(self.sidebar)

        self.list = ui.FileView(
            self._activate_row, self.go_up, self._open_in_new_tab,
            self._on_drop_files, self._on_drag_hover,
        )
        self.list.setModel(self.model)
        self.list.apply_metrics()
        self.list.header().sectionClicked.connect(self._on_header)

        self.icons = ui.IconView(
            self._activate_row, self.go_up, self._open_in_new_tab,
            self._on_drop_files, self._on_drag_hover,
        )
        self.icons.setModel(self.model)
        # 選択状態を共有する。表示を切り替えても選択が飛ばない。
        self.icons.setSelectionModel(self.list.selectionModel())
        self.icons.icon_size_changed.connect(self._on_icon_size)
        self.list.selectionModel().selectionChanged.connect(lambda *_: self._update_status())

        for v in (self.list, self.icons):
            v.customContextMenuRequested.connect(
                lambda pos, view=v: self._context_menu(view, pos)
            )
        self.model.rename_requested.connect(self._do_rename)

        self.views = QStackedWidget()
        self.views.addWidget(self.list)
        self.views.addWidget(self.icons)
        split.addWidget(self.views)
        split.setStretchFactor(1, 1)
        split.setSizes([theme.SIDEBAR_WIDTH, 700])
        outer.addWidget(split, 1)

        header = self.list.header()
        header.setSortIndicatorShown(True)
        header.setSortIndicator(ui.COL_NAME, Qt.SortOrder.AscendingOrder)

        self.status = QLabel(objectName="Status")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.status)

        self.setCentralWidget(root)
        self._sort_key, self._sort_reverse = "name", False

    def _fill_sidebar(self):
        self.sidebar.clear()
        for is_head, label, path in places():
            item = QListWidgetItem(label)
            if is_head:
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                f = item.font()
                f.setPointSize(max(theme.FONT_SIZE - 1, 7))
                item.setFont(f)
            else:
                item.setData(Qt.ItemDataRole.UserRole, path)
                item.setIcon(self.model.icons.for_path(path))
                # ドライブルート（例: "C:\\"）にはディスク情報を付加する
                if path and len(os.path.splitdrive(path)[1].rstrip("\\/")) == 0:
                    info = osops.disk_info(path)
                    item.setData(_DRIVE_INFO, info)
                    item.setSizeHint(QSize(0, 30))
            self.sidebar.addItem(item)

    def _sidebar_ctx_menu(self, pos):
        item = self.sidebar.itemAt(pos)
        if item is None:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if path is None:
            return   # 見出し行は無視する

        menu = QMenu(self)
        menu.addAction("新しいタブで開く", lambda: self.new_tab(path))
        if self._is_ejectable(path, item.data(_DRIVE_INFO)):
            menu.addAction("取り外す", lambda: self._eject(path))
        menu.addSeparator()
        menu.addAction("プロパティ", lambda: osops.properties(
            path, int(self.winId())
        ))
        menu.exec(self.sidebar.viewport().mapToGlobal(pos))

    @staticmethod
    def _is_ejectable(path, info):
        """USB メモリ・SD カード・USB 接続のディスクなら取り外せる。内蔵ディスクは出さない。"""
        if not path or os.path.splitdrive(path)[1].rstrip("\\/"):
            return False   # ドライブのルートだけ
        if _drive_type(path) == 2:
            return True
        return bool(info) and info.get("bus") in ("USB", "SD", "MMC", "IEEE1394")

    def _eject(self, path):
        """取り外す。先に全部の窓でそのドライブを離れて、自分が掴んでいる状態をなくす。"""
        drive = os.path.splitdrive(path)[0].upper()
        home = os.path.expanduser("~")
        for win in WINDOWS:
            for i, tab in enumerate(win._tabs):
                if os.path.splitdrive(tab["path"])[0].upper() != drive:
                    continue
                if i == win.tabbar.currentIndex():
                    win.navigate(home)
                else:
                    tab["path"] = home
                    win.tabbar.setTabText(i, win._tab_label(home))
                    win.tabbar.setTabToolTip(i, home)
        self.status.setText(f"{drive} を取り外しています…")
        QApplication.processEvents()
        err = osops.eject_drive(path)
        if err:
            self.status.setText(f"{drive} を取り外せません — {err}")
        else:
            self.status.setText(f"{drive} を取り外しました。安全に抜けます")
            QTimer.singleShot(400, self._fill_sidebar)

    # --- テーマ -------------------------------------------------------------
    def _apply_theme(self):
        self.setStyleSheet(theme.build_qss(self._theme))
        self.model.set_palette(self._theme)

    def _set_theme(self, name):
        self._theme = name
        self._apply_theme()
        self.reload()

    # --- 画面遷移 -----------------------------------------------------------
    def navigate(self, path, record=True):
        path = os.path.abspath(path)
        try:
            entries, skipped = core.list_dir(path, self._show_hidden)
        except OSError as e:
            # 失敗したら現在地を動かさない。サイドバーの選択も元に戻す。
            self.status.setText(f"開けません: {e.strerror or e}")
            self._sync_sidebar()
            return
        tab = self._current_tab()
        if record and self._path and tab:
            tab["history"].append(self._path)
            tab["future"].clear()
        self._path = path
        if tab:
            tab["path"] = path
            idx = self.tabbar.currentIndex()
            self.tabbar.setTabText(idx, self._tab_label(path))
            self.tabbar.setTabToolTip(idx, path)

        self.model.load(entries, skipped)
        view = self._current_view()
        view.scrollToTop()
        if self.model.rowCount():
            view.setCurrentIndex(self.model.index(0, 0))
        self._update_address()
        self._update_status()
        self._update_buttons()
        self._sync_sidebar()
        self.setWindowTitle(f"{os.path.basename(path) or path} — Filer")

    # --- タブ ---------------------------------------------------------------
    def new_tab(self, path=None, switch=True):
        path = path or self._path or os.path.expanduser("~")
        self._tabs.append({"path": path, "history": [], "future": []})
        idx = self.tabbar.addTab(self._tab_label(path))
        self.tabbar.setTabToolTip(idx, path)
        if switch:
            self.tabbar.setCurrentIndex(idx)
        refresh_chaos()
        return idx

    def close_current_tab(self):
        self.close_tab(self.tabbar.currentIndex())

    def close_tab(self, index):
        if not 0 <= index < len(self._tabs):
            return
        if len(self._tabs) == 1:
            self.close()  # 最後の一枚を閉じたら窓ごと閉じる（Chrome と同じ）
            return
        self._closed.append(self._tabs[index])
        del self._tabs[index]
        self.tabbar.removeTab(index)
        refresh_chaos()

    def reopen_tab(self):
        if not self._closed:
            return
        state = self._closed.pop()
        self._tabs.append(state)
        idx = self.tabbar.addTab(self._tab_label(state["path"]))
        self.tabbar.setTabToolTip(idx, state["path"])
        self.tabbar.setCurrentIndex(idx)

    # --- 窓をまたぐタブの移動 -----------------------------------------------
    def new_window(self):
        open_window(self._path, at=self.pos() + QPoint(32, 32))

    def _take_tab(self, index):
        """タブを取り外し、控えの鍵を返す。ドラッグの開始時に呼ばれる。"""
        state = self._tabs.pop(index)
        self.tabbar.removeTab(index)
        key = uuid.uuid4().hex
        PENDING_TABS[key] = state
        return key

    def _adopt_tab(self, key, index):
        """他の窓から来たタブを受け取る。"""
        state = PENDING_TABS.pop(key, None)
        if not state:
            return
        # -1 は末尾（タブバー以外の場所に落とされたとき）
        index = len(self._tabs) if index < 0 else max(0, min(index, len(self._tabs)))
        self._tabs.insert(index, state)
        self.tabbar.insertTab(index, self._tab_label(state["path"]))
        self.tabbar.setTabToolTip(index, state["path"])
        self.tabbar.setCurrentIndex(index)
        self.raise_()
        self.activateWindow()
        refresh_chaos()

    def _spawn_window(self, key, pos):
        """どの窓にも落とされなかったタブを、その場で独立させる。"""
        state = PENDING_TABS.pop(key, None)
        if not state:
            return
        win = open_window(state["path"], at=pos - QPoint(60, 12))
        # 履歴も引き継ぐ。移した先で戻れないと、ただのコピーになってしまう。
        win._tabs[0]["history"] = state["history"]
        win._tabs[0]["future"] = state["future"]
        win._update_buttons()

    def closeEvent(self, event):
        # 最後の一枚を閉じるときに状態を覚えておく。次の起動でこの窓とタブが戻る（Chrome と同じ）。
        if WINDOWS == [self]:
            save_session()
        if self in WINDOWS:
            WINDOWS.remove(self)
        refresh_chaos()
        super().closeEvent(event)

    # --- 状態の保存と復元 ---------------------------------------------------
    def session_state(self):
        """この窓を元通りに作り直すのに要るものを辞書にする。"""
        limit = session.HISTORY_LIMIT
        return {
            "geometry": bytes(self.saveGeometry().toBase64()).decode("ascii"),
            "tabs": [{"path": t["path"],
                      "history": t["history"][-limit:],
                      "future": t["future"][-limit:]} for t in self._tabs],
            "current": self.tabbar.currentIndex(),
            "view_mode": self._view_mode,
            "icon_step": self.icons.size_step(),
            "show_hidden": self._show_hidden,
            "theme": self._theme,
            "sort": [self._sort_key, self._sort_reverse],
            "active": self.isActiveWindow(),
        }

    def apply_state(self, state):
        """session_state で作った辞書を当てはめる。一枚目のタブは作成時に開いている前提。"""
        tabs = [t for t in state.get("tabs", []) if isinstance(t, dict)]
        fix = session.existing_dir
        for i, t in enumerate(tabs):
            path = fix(t.get("path"))
            if i == 0:
                self._tabs[0]["path"] = path
            else:
                self.new_tab(path, switch=False)
            self._tabs[i]["history"] = [p for p in t.get("history", []) if isinstance(p, str)]
            self._tabs[i]["future"] = [p for p in t.get("future", []) if isinstance(p, str)]

        if state.get("theme") in theme.PALETTES and state["theme"] != self._theme:
            self._theme_actions[state["theme"]].setChecked(True)
            self._theme = state["theme"]
            self._apply_theme()
        if bool(state.get("show_hidden")) != self._show_hidden:
            self.act_hidden.setChecked(bool(state.get("show_hidden")))
            self._show_hidden = bool(state.get("show_hidden"))
        sort = state.get("sort")
        if isinstance(sort, list) and len(sort) == 2 and sort[0] in ui.SORT_KEYS.values():
            self._sort_key, self._sort_reverse = sort[0], bool(sort[1])
            self.model.set_sort(self._sort_key, self._sort_reverse)
            col = next(c for c, k in ui.SORT_KEYS.items() if k == self._sort_key)
            order = (Qt.SortOrder.DescendingOrder if self._sort_reverse
                     else Qt.SortOrder.AscendingOrder)
            self.list.header().setSortIndicator(col, order)
        if isinstance(state.get("icon_step"), int):
            self.icons.set_size_step(state["icon_step"])
        if state.get("view_mode") in ("list", "icons"):
            self._set_view_mode(state["view_mode"])

        current = state.get("current", 0)
        current = current if isinstance(current, int) and 0 <= current < len(self._tabs) else 0
        self._switching = True
        self.tabbar.setCurrentIndex(current)
        self._switching = False
        self.navigate(self._tabs[current]["path"], record=False)

        geo = state.get("geometry")
        if isinstance(geo, str):
            self.restoreGeometry(QByteArray.fromBase64(geo.encode("ascii")))

    def _select_tab(self, index):
        if 0 <= index < len(self._tabs):
            self.tabbar.setCurrentIndex(index)

    def _step_tab(self, delta):
        count = len(self._tabs)
        if count > 1:
            self.tabbar.setCurrentIndex((self.tabbar.currentIndex() + delta) % count)

    def _on_tab_changed(self, index):
        if not 0 <= index < len(self._tabs) or self._switching:
            return
        self._switching = True
        try:
            self.navigate(self._tabs[index]["path"], record=False)
        finally:
            self._switching = False

    def _tab_label(self, path):
        return os.path.basename(path.rstrip(os.sep)) or path.rstrip(os.sep) or path

    def _current_tab(self):
        idx = self.tabbar.currentIndex()
        if 0 <= idx < len(self._tabs):
            return self._tabs[idx]
        return None

    # --- 右クリックメニュー -------------------------------------------------
    def _context_menu(self, view, pos):
        index = view.indexAt(pos)
        menu = QMenu(self)

        if index.isValid():
            e = self.model.entry(index.row())
            if e:
                # アクセラレータは Explorer に合わせる。指が覚えているので変えない。
                menu.addAction("開く(&O)", lambda: self._activate_row(index.row()))
                if e.is_dir:
                    menu.addAction("新しいタブで開く(&W)", lambda: self.new_tab(e.path))
                menu.addSeparator()
                menu.addAction("切り取り(&T)", self.cut_selected)
                menu.addAction("コピー(&C)", self.copy_selected)
                menu.addSeparator()
                menu.addAction("名前の変更(&M)", lambda: self._edit_index(index))
                menu.addAction("削除(&D)", self.delete_selected)
                menu.addSeparator()
                menu.addAction("プロパティ(&R)", lambda: self._properties(e.path))
        else:
            menu.addAction("貼り付け(&P)", self.paste_here)
            menu.addSeparator()
            menu.addAction("新しいタブ(&T)", lambda: self.new_tab(self._path))
            menu.addAction("最新の情報に更新(&R)", self.reload)
            menu.addSeparator()
            menu.addAction("プロパティ(&R)", lambda: self._properties(self._path))

        if not menu.isEmpty():
            menu.exec(view.viewport().mapToGlobal(pos))

    def _properties(self, path):
        reason = osops.properties(path, int(self.winId()))
        if reason:
            self.status.setText(reason)

    def properties_selected(self):
        paths = self._selected_paths()
        self._properties(paths[0] if paths else self._path)

    # --- コピー / 切り取り / 貼り付け ---------------------------------------
    def _selected_paths(self):
        rows = {i.row() for i in self._current_view().selectionModel().selectedIndexes()}
        return [self.model.entry(r).path for r in sorted(rows) if self.model.entry(r)]

    def copy_selected(self):
        paths = self._selected_paths()
        if not paths:
            return
        fileops.put_clipboard(paths, move=False)
        self.model.set_cut([])
        self.status.setText(f"コピーの準備をしました: {len(paths)} 項目")

    def cut_selected(self):
        paths = self._selected_paths()
        if not paths:
            return
        fileops.put_clipboard(paths, move=True)
        # この時点では何も消えない。薄く表示して「予約済み」であることだけ示す。
        self.model.set_cut(paths)
        self.status.setText(f"移動の準備をしました: {len(paths)} 項目（貼り付けるまで動きません）")

    def paste_here(self):
        paths, move = fileops.read_clipboard()
        if not paths:
            self.status.setText("貼り付けるものがありません")
            return
        if self._transfer(paths, self._path, move) and move:
            # 移動が済んだらクリップボードを空にする。残すと二重に動かそうとする。
            fileops.clear_clipboard()
            self.model.set_cut([])

    def _transfer(self, paths, dest, move):
        """コピーまたは移動を実行する。成功したら True。

        貼り付けもドラッグも最後はここに来る。判断を一箇所にまとめておく。
        """
        verb = "移動" if move else "コピー"
        dest = os.path.abspath(dest)

        # 自分の中に自分を入れようとしていないか先に見る
        for p in paths:
            if os.path.normcase(dest).startswith(os.path.normcase(p) + os.sep):
                self.status.setText(f"{os.path.basename(p)} の中へは入れられません")
                return False
        # 元の場所と同じなら何もしない
        if all(os.path.normcase(os.path.dirname(p)) == os.path.normcase(dest)
               for p in paths) and move:
            self.status.setText("同じ場所です")
            return False

        self.status.setText(f"{verb}しています: {len(paths)} 項目 → {dest}")
        op = osops.move_files if move else osops.copy_files
        reason = op(paths, dest, int(self.winId()))
        if reason:
            self.status.setText(f"{verb}できません: {reason}")
            return False

        self.reload()
        self.status.setText(f"{verb}しました: {len(paths)} 項目 → {dest}")
        return True

    # --- ドラッグで移動 -----------------------------------------------------
    def _drop_target(self, row):
        """落とした先のフォルダ。フォルダの上ならその中、それ以外は今の場所。"""
        e = self.model.entry(row) if row >= 0 else None
        return e.path if (e and e.is_dir) else self._path

    def _on_drag_hover(self, row, copy):
        """何が起きるかを常に見せる。Windows の見えない分岐を持ち込まないため。"""
        dest = self._drop_target(row)
        verb = "コピー" if copy else "移動"
        hint = "" if copy else "（Ctrl でコピー）"
        self.status.setText(f"{verb}します → {dest} {hint}")

    def _on_drop_files(self, paths, row, copy):
        self._transfer(paths, self._drop_target(row), move=not copy)

    def delete_selected(self):
        paths = self._selected_paths()
        if not paths:
            return
        reason = osops.delete_files(paths, int(self.winId()))
        if reason:
            self.status.setText(f"削除できません: {reason}")
            return
        self.reload()
        self.status.setText(f"ゴミ箱へ移動しました: {len(paths)} 項目")

    # --- 名前の変更 ---------------------------------------------------------
    def rename_selected(self):
        view = self._current_view()
        index = view.currentIndex()
        if index.isValid():
            self._edit_index(index)

    def _edit_index(self, index):
        view = self._current_view()
        target = self.model.index(index.row(), ui.COL_NAME)
        view.setCurrentIndex(target)
        view.edit(target)

    def _do_rename(self, entry, new_name):
        new_path, reason = fileops.rename(entry.path, new_name)
        if reason:
            self.status.setText(f"変更できません: {reason}")
            return
        self.reload()
        self._select_name(os.path.basename(new_path))
        self.status.setText(f"名前を変更しました: {os.path.basename(new_path)}")

    def _on_icon_size(self, px):
        self.status.setText(f"アイコンの大きさ: {px}px")
        self._update_thumbs()

    def _update_thumbs(self):
        """サムネイルは大きいアイコン表示のときだけ出す。

        一覧表示の 16px で中身を見せても意味が無いし、小さいアイコンでも同じ。
        無駄な生成を走らせないよう、そもそも頼まない。
        """
        if self._view_mode == "icons":
            size = self.icons.iconSize().width()
            box = size if size >= theme.THUMB_MIN_SIZE else 0
        else:
            box = 0
        self.model.set_thumb_box(box)

    def _set_view_mode(self, mode):
        self._view_mode = mode
        is_list = mode == "list"
        self.btn_list.setChecked(is_list)
        self.btn_icons.setChecked(not is_list)
        target = self.list if is_list else self.icons
        self.views.setCurrentWidget(target)
        target.setFocus()
        self._update_thumbs()

    def _current_view(self):
        return self.list if self._view_mode == "list" else self.icons

    def _sync_sidebar(self):
        """サイドバーの選択を実際の現在地に合わせる。一致が無ければ選択を外す。"""
        self.sidebar.blockSignals(True)
        self.sidebar.clearSelection()
        for i in range(self.sidebar.count()):
            item = self.sidebar.item(i)
            path = item.data(Qt.ItemDataRole.UserRole)
            if path and os.path.normcase(os.path.abspath(path)) == os.path.normcase(
                self._path or ""
            ):
                item.setSelected(True)
                self.sidebar.setCurrentItem(item)
                break
        self.sidebar.blockSignals(False)

    def reload(self):
        if self._path:
            self.navigate(self._path, record=False)

    def go_back(self):
        tab = self._current_tab()
        if tab and tab["history"]:
            tab["future"].append(self._path)
            self.navigate(tab["history"].pop(), record=False)

    def go_forward(self):
        tab = self._current_tab()
        if tab and tab["future"]:
            tab["history"].append(self._path)
            self.navigate(tab["future"].pop(), record=False)

    def go_up(self):
        if not self._path:
            return
        child_name = os.path.basename(self._path.rstrip(os.sep))
        # rstrip してから dirname すると "C:\\" → "C:" → dirname("C:") = "C:" となり
        # "C:" != "C:\\" が True になって誤ナビゲートするので rstrip しない
        parent = os.path.dirname(self._path)
        if parent and parent != self._path:
            self.navigate(parent)
            if child_name:
                self._select_name(child_name)

    def _activate_row(self, row):
        e = self.model.entry(row)
        if not e:
            return
        if e.is_dir:
            self.navigate(e.path)
            return
        try:
            osops.open_path(e.path)
        except OSError as err:
            self.status.setText(f"開けません: {err.strerror or err}")

    def _open_in_new_tab(self, row):
        """中クリック用。フォルダだけ新しいタブで開く。

        ファイルまで開くと、押し間違いで勝手にアプリが立ち上がって驚くので開かない。
        """
        e = self.model.entry(row)
        if e and e.is_dir:
            self.new_tab(e.path)

    def _on_place(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.navigate(path)

    def _on_header(self, col):
        key = ui.SORT_KEYS.get(col)
        if not key:
            return
        if key == self._sort_key:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_key, self._sort_reverse = key, False
        self.model.set_sort(self._sort_key, self._sort_reverse)
        order = Qt.SortOrder.DescendingOrder if self._sort_reverse else Qt.SortOrder.AscendingOrder
        self.list.header().setSortIndicator(col, order)
        self._update_status()

    def _on_filter(self, text):
        self.model.set_filter(text)
        self._update_status()

    def _toggle_hidden(self, checked):
        self._show_hidden = checked
        self.reload()

    # --- 表示の更新 ---------------------------------------------------------
    def _update_address(self):
        """編集中は書き換えない。入力の途中で奪われると腹が立つので。"""
        if not self.address.hasFocus():
            self.address.setText(self._path)

    def _focus_address(self):
        self.address.setFocus()
        self.address.selectAll()

    def _focus_search(self):
        self.search.setFocus()
        self.search.selectAll()

    def _commit_path(self):
        target = os.path.expandvars(self.address.text().strip().strip('"'))
        if not target:
            return
        if os.path.isdir(target):
            self._current_view().setFocus()
            self.navigate(target)
        elif os.path.isfile(target):
            # ファイルを指されたら、その親へ移動して選択してやる
            self._current_view().setFocus()
            self.navigate(os.path.dirname(target))
            self._select_name(os.path.basename(target))
        else:
            self.status.setText(f"見つかりません: {target}")

    def _select_name(self, name):
        for row in range(self.model.rowCount()):
            e = self.model.entry(row)
            if e and e.name == name:
                idx = self.model.index(row, 0)
                view = self._current_view()
                view.setCurrentIndex(idx)
                view.scrollTo(idx)
                return

    def _update_status(self):
        total = self.model.rowCount()
        selected = len(self.list.selectionModel().selectedRows())
        bits = [f"{total} 項目"]
        if selected > 1:
            bits.append(f"{selected} 個を選択")
        if self.model.skipped:
            bits.append(f"{self.model.skipped} 件は読めません")
        try:
            free = shutil.disk_usage(self._path).free / (1024 ** 3)
            bits.append(f"空き {free:.1f} GB")
        except OSError:
            pass
        self.status.setText(" — ".join(bits))

    def _update_buttons(self):
        tab = self._current_tab() or {"history": [], "future": []}
        for btn, act, on in (
            (self.btn_back, self.act_back, bool(tab["history"])),
            (self.btn_fwd, self.act_fwd, bool(tab["future"])),
        ):
            btn.setEnabled(on)
            act.setEnabled(on)


def save_session(path=None):
    """開いている全部の窓の状態を書く。窓が一枚も無ければ何もしない（空で上書きしない）。"""
    if not WINDOWS:
        return
    try:
        session.save([w.session_state() for w in WINDOWS], path)
    except OSError:
        pass   # 覚えられなくても終了や再起動は止めない


def restore_windows(states):
    """保存された窓を作り直す。一枚も作れなければ False。"""
    active = None
    for state in states:
        if not isinstance(state, dict) or not state.get("tabs"):
            continue
        first = session.existing_dir(state["tabs"][0].get("path"))
        win = open_window(first)
        win.apply_state(state)
        if state.get("active"):
            active = win
    if active is not None:
        active.raise_()
        active.activateWindow()
    refresh_chaos()
    return bool(WINDOWS)


def restart_self():
    """状態を受け渡し用のファイルに書き、自分をもう一つ起動してから終わる。"""
    path = session.temp_path()
    save_session(path)
    osops.relaunch(["--restore", path])
    QApplication.quit()


def _busy_reason():
    """今は終われない理由。終われるなら None。

    名前の変更などのダイアログやメニューを開いている最中に消えると、
    入力の途中の内容が黙って失われる。そういうときは断る。
    コピー・移動の最中は OS のダイアログが処理を握っているので、そもそも返事ができない
    （頼んだ側が時間切れで諦める）。
    """
    if QApplication.activeModalWidget() is not None:
        return "ダイアログを開いています"
    if QApplication.activePopupWidget() is not None:
        return "メニューを開いています"
    return None


def _on_quit_request(path):
    reason = _busy_reason()
    if reason:
        return reason
    save_session(path)
    return None


def _parse_args(argv):
    """[フォルダ] か --restore [状態ファイル]。フォルダを渡されたときは復元しない。"""
    args = argv[1:]
    if args and args[0] == "--restore":
        return None, (args[1] if len(args) > 1 else None), True
    return (args[0] if args else None), None, False


def main():
    start, restore_from, forced = _parse_args(sys.argv)
    app = QApplication(sys.argv)
    app.setApplicationName("Filer")
    # トレイの「終了」など、窓を閉じずに終わる経路でも状態を覚える
    app.aboutToQuit.connect(save_session)
    control.start(_on_quit_request)

    restored = False
    if start is None:
        # 受け渡し用のファイルは読んだら消す。いつもの保存先は残す。
        states = session.load(restore_from, remove=bool(restore_from))
        restored = restore_windows(states)
    if not restored:
        open_window(start or os.path.expanduser("~"))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
