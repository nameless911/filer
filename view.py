"""一覧の描画部分。Qt に触るのはここだけ。

Qt の役割は「渡された行を描く」「入力を返す」に限定する。
並び順や表示文字列の判断は model.py が持っているので、ここには書かない。
"""

import os

from PySide6.QtCore import (
    QAbstractTableModel,
    QEvent,
    QFileInfo,
    QMimeData,
    QModelIndex,
    QPoint,
    QRect,
    QSize,
    QUrl,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QCursor, QDrag, QMouseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileIconProvider,
    QHeaderView,
    QListView,
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QTabBar,
    QTreeView,
    QWidget,
)

import model as core
import osops
import theme
import thumbs

COL_NAME, COL_SIZE, COL_TYPE, COL_DATE, COL_ATTR = 0, 1, 2, 3, 4
HEADERS = ("名前", "サイズ", "種類", "更新日時", "属性")

# 列ヘッダのクリックで使う並び替えキー。
# 種類は表示名ではなく拡張子で並べる（同じ種類は必ず隣り合うので実用上は同じ）。
SORT_KEYS = {
    COL_NAME: "name",
    COL_SIZE: "size",
    COL_TYPE: "ext",
    COL_DATE: "mtime",
    COL_ATTR: "attr",
}


TAB_MIME = "application/x-filer-tab"

# タブバーからこれだけ縦に離れたら「引き剥がし」とみなす。
# 横方向の移動は並べ替えなので、縦だけを見る。
TEAR_MARGIN = 24


class DropTitleBar(QWidget):
    """タイトルバー全域でタブを受ける。

    タブバーの細い帯だけを狙わせるのは酷なので、上端の帯ならどこでも受理する。
    タブバーの上に落ちた場合は、そちらが先に受け取って挿し込み位置まで決める。
    """

    def __init__(self, parent=None, object_name="TitleBar"):
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setAcceptDrops(True)
        self.adopt_tab = None  # (key, index) index が -1 なら末尾

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(TAB_MIME) and self.adopt_tab:
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
            return
        event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        data = event.mimeData().data(TAB_MIME)
        if not data or not self.adopt_tab:
            event.ignore()
            return
        self.adopt_tab(bytes(data).decode(), -1)
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()


class TabBar(QTabBar):
    """タブの並び。中クリックで閉じ、外へ引き出すと別ウィンドウになる。

    窓をまたぐ移動は Qt のドラッグ＆ドロップに乗せる。
    受け側のタブバーが受理すればそちらへ移り、誰も受けなければ新しい窓になる。

    使う側は take_tab / adopt_tab / spawn_window を差してから使うこと。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Tabs")
        self.setAcceptDrops(True)
        self._press_index = -1
        self._tearing = False
        # 差し込み口。main 側がタブの中身を知っているので、そちらに任せる。
        self.take_tab = None      # (index) -> key   タブを取り外して控えを返す
        self.adopt_tab = None     # (key, index)     控えを受け取って差し込む
        self.spawn_window = None  # (key, global_pos) 新しい窓にする
        self.setTabsClosable(True)
        self.setMovable(True)
        self.setExpanding(False)
        self.setDocumentMode(True)
        self.setDrawBase(False)
        self.setElideMode(Qt.TextElideMode.ElideRight)
        self.setUsesScrollButtons(True)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            idx = self.tabAt(event.position().toPoint())
            if idx >= 0:
                self.tabCloseRequested.emit(idx)
                return
        self._press_index = -1
        self._tearing = False
        super().mouseReleaseEvent(event)

    # --- 引き剥がし ---------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_index = self.tabAt(event.position().toPoint())
            self._tearing = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._should_tear(event):
            self._start_tear(event)
            return
        super().mouseMoveEvent(event)

    def _should_tear(self, event):
        if self._tearing or self._press_index < 0:
            return False
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return False
        if self.count() < 1 or self.take_tab is None:
            return False
        y = event.position().toPoint().y()
        return y < -TEAR_MARGIN or y > self.height() + TEAR_MARGIN

    def _start_tear(self, event):
        self._tearing = True
        index = self._press_index
        self._press_index = -1

        # 見た目用の絵は取り外す前に取る
        pixmap = self.grab(self.tabRect(index))

        # QTabBar 内部の並べ替え状態を終わらせる。放置すると掴んだままになる。
        release = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            event.position(),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        super().mouseReleaseEvent(release)

        key = self.take_tab(index)
        mime = QMimeData()
        mime.setData(TAB_MIME, key.encode())

        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))
        result = drag.exec(Qt.DropAction.MoveAction)

        if result == Qt.DropAction.MoveAction:
            if self.count() == 0:
                # 空になった窓は畳む。今のイベント処理が終わってから消すこと
                # （処理の途中で自分を消すと落ちる）。
                QTimer.singleShot(0, self.window().close)
            return

        # 誰も受け取らなかった場合
        if self.count() == 0 and self.adopt_tab:
            self.adopt_tab(key, 0)  # 最後の一枚だったので元に戻す
        elif self.spawn_window:
            self.spawn_window(key, QCursor.pos())

    # --- 受け入れ -----------------------------------------------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(TAB_MIME) and self.adopt_tab:
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
            return
        event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(TAB_MIME):
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
            return
        event.ignore()

    def dropEvent(self, event):
        data = event.mimeData().data(TAB_MIME)
        if not data or not self.adopt_tab:
            event.ignore()
            return
        pos = event.position().toPoint()
        index = self.tabAt(pos)
        if index < 0:
            index = self.count()  # タブの無い場所に落としたら末尾へ
        self.adopt_tab(bytes(data).decode(), index)
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()


class IconSource:
    """Explorer と同じアイコンを引く。中身は Windows のシェル問い合わせ。

    一件ずつ問い合わせると遅いので拡張子ごとに覚える。
    ただし実行ファイルやショートカットは1つ1つ絵が違うので、都度引く。
    """

    # 中身ごとに固有のアイコンを持つもの。キャッシュすると全部同じ絵になってしまう。
    PER_FILE = {".exe", ".lnk", ".ico", ".msi", ".scr", ".cpl", ".url", ".appref-ms"}

    def __init__(self):
        self._provider = QFileIconProvider()
        self._by_ext = {}
        self._type_by_ext = {}
        self._dir_type = osops.type_name(os.sep, is_dir=True) or "フォルダー"
        self._folder = self._provider.icon(QFileIconProvider.IconType.Folder)
        self._file = self._provider.icon(QFileIconProvider.IconType.File)

    def for_entry(self, e):
        if e.is_dir:
            return self._folder
        ext = e.ext
        if ext in self.PER_FILE:
            return self._lookup(e.path) or self._file
        icon = self._by_ext.get(ext)
        if icon is None:
            icon = self._lookup(e.path) or self._file
            self._by_ext[ext] = icon
        return icon

    def for_path(self, path):
        """サイドバー用。項目数が少ないので毎回引いてよい。"""
        return self._lookup(path) or self._folder

    def type_for(self, e):
        """「PDF ファイル」等の種類名。Explorer の「種類」列と同じ出所。"""
        if e.is_dir:
            return self._dir_type
        ext = e.ext
        name = self._type_by_ext.get(ext)
        if name is None:
            name = osops.type_name(e.path) or self._provider.type(QFileInfo(e.path))
            if not name:
                name = f"{ext[1:].upper()} ファイル" if ext else "ファイル"
            self._type_by_ext[ext] = name
        return name

    def _lookup(self, path):
        icon = self._provider.icon(QFileInfo(path))
        return None if icon.isNull() else icon


class FileTableModel(QAbstractTableModel):
    # 名前の編集が確定したときに飛ぶ。実際の改名は main 側で行う。
    # モデルにファイル操作をさせないこと（判断の置き場所を一つに保つため）。
    rename_requested = Signal(object, str)

    def __init__(self, palette_name=theme.DEFAULT_THEME, parent=None):
        super().__init__(parent)
        self._all = []        # 読み込んだ全件
        self._rows = []       # 絞り込み後の表示対象
        self._filter = ""
        self._sort_key = "name"
        self._reverse = False
        self.skipped = 0
        # 切り取り中のパス。薄く描くためだけに使う。ファイルには何の印も付かない。
        self._cut = set()
        # アイコンはテーマ切り替えで消さないよう、set_palette からは触らないこと。
        self.icons = IconSource()
        # サムネイルは大きいアイコン表示のときだけ。0 なら使わない。
        self.thumb_box = 0
        self.thumbs = thumbs.ThumbnailCache(self)
        self.thumbs.ready.connect(self._thumb_ready)
        self.set_palette(palette_name)

    # --- 見た目 ---
    def set_palette(self, name):
        p = theme.PALETTES[name]
        self._dim = QColor(p["row_dim"])
        cut = QColor(p["row_dim"])
        cut.setAlpha(120)  # さらに薄く。切り取り中であることが一目で分かる程度に。
        self._cut_color = cut

    # --- 中身の入れ替え ---
    def load(self, entries, skipped=0):
        # 場所が変わったので、走っている生成の結果はもう要らない
        self.thumbs.invalidate()
        self.beginResetModel()
        self._all = entries
        self.skipped = skipped
        self._apply()
        self.endResetModel()

    def set_filter(self, text):
        self.beginResetModel()
        self._filter = text.strip().lower()
        self._apply()
        self.endResetModel()

    def set_sort(self, key, reverse):
        self.beginResetModel()
        self._sort_key, self._reverse = key, reverse
        self._apply()
        self.endResetModel()

    def _apply(self):
        rows = self._all
        if self._filter:
            rows = [e for e in rows if self._filter in e.name.lower()]
        self._rows = core.sort_entries(rows, self._sort_key, self._reverse)

    def set_thumb_box(self, box):
        """サムネイルの一辺。0 で無効。切り替えたら描き直す。"""
        if box == self.thumb_box:
            return
        self.thumb_box = box
        self._redraw_icons()

    def _thumb_ready(self, path):
        """出来たものだけ差し替える。全体を作り直さない。"""
        key = os.path.normcase(path)
        for row, e in enumerate(self._rows):
            if os.path.normcase(e.path) == key:
                idx = self.index(row, COL_NAME)
                self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DecorationRole])
                return

    def _redraw_icons(self):
        if not self.rowCount():
            return
        top = self.index(0, COL_NAME)
        bottom = self.index(self.rowCount() - 1, COL_NAME)
        self.dataChanged.emit(top, bottom, [Qt.ItemDataRole.DecorationRole])

    def set_cut(self, paths):
        self._cut = {os.path.normcase(p) for p in paths}
        if self.rowCount():
            top = self.index(0, 0)
            bottom = self.index(self.rowCount() - 1, self.columnCount() - 1)
            self.dataChanged.emit(top, bottom, [Qt.ItemDataRole.ForegroundRole])

    def is_cut(self, entry):
        return os.path.normcase(entry.path) in self._cut

    def entry(self, row):
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    # --- Qt から呼ばれる ---
    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return HEADERS[section]
        # 値と見出しの寄せは揃える（揃っていないと安っぽく見える）
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if section == COL_SIZE:
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if section == COL_ATTR:
                return int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ToolTipRole and section == COL_ATTR:
            return "R=読取専用 A=アーカイブ H=隠し S=システム\nC=圧縮 E=暗号化 L=リンク O=クラウドのみ"
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        e = self._rows[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == COL_NAME:
                return e.name
            if col == COL_SIZE:
                return core.format_size(e.size)
            if col == COL_TYPE:
                return self.icons.type_for(e)
            if col == COL_ATTR:
                return core.attr_letters(e.attrs)
            return core.format_mtime(e.mtime)

        if role == Qt.ItemDataRole.DecorationRole and col == COL_NAME:
            # ここが呼ばれるのは画面に映る行だけ。先読みは自然と起きない。
            if self.thumb_box:
                thumb = self.thumbs.get(e, self.thumb_box)
                if thumb is not None:
                    return thumb
            # 出来るまでは種類アイコンを出す。空白にすると落ち着かないので。
            return self.icons.for_entry(e)

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col == COL_SIZE:
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if col == COL_ATTR:
                return int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)

        if role == Qt.ItemDataRole.ForegroundRole:
            # 切り取り中は全列を薄く。貼り付けるまで実体は元の場所にある。
            if self.is_cut(e):
                return self._cut_color
            if col != COL_NAME:
                return self._dim

        if role == Qt.ItemDataRole.EditRole and col == COL_NAME:
            return e.name

        if role == Qt.ItemDataRole.ToolTipRole and e.placeholder:
            return "クラウド上のみに存在します（開くと同期が走ります）"

        return None

    def flags(self, index):
        base = super().flags(index)
        if not index.isValid():
            return base
        base |= Qt.ItemFlag.ItemIsDragEnabled
        if index.column() == COL_NAME:
            base |= Qt.ItemFlag.ItemIsEditable
        return base

    # --- 持ち出し -----------------------------------------------------------
    # これがあると Explorer や他のアプリへそのままドラッグして渡せる。
    def mimeTypes(self):
        return ["text/uri-list"]

    def supportedDragActions(self):
        return Qt.DropAction.MoveAction | Qt.DropAction.CopyAction

    def mimeData(self, indexes):
        rows = sorted({i.row() for i in indexes if i.isValid()})
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(self._rows[r].path) for r in rows])
        return mime

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole or index.column() != COL_NAME:
            return False
        e = self._rows[index.row()]
        new_name = str(value).strip()
        if not new_name or new_name == e.name:
            return False
        self.rename_requested.emit(e, new_name)
        return False  # 実際の反映は改名の成否を見てから再読み込みで行う


class NameEditDelegate(QStyledItemDelegate):
    """名前を編集するとき、拡張子を除いた部分だけ選択しておく。

    Explorer と同じ挙動。体に染み付いているので、違うと地味に効く。
    """

    def setEditorData(self, editor, index):
        super().setEditorData(editor, index)
        text = editor.text() if hasattr(editor, "text") else ""
        stem = os.path.splitext(text)[0]
        if stem and stem != text:
            editor.setSelection(0, len(stem))


_BREAK_AFTER = " -_.)]"   # ここの直後で折り返せるなら優先する


def wrap_name(text, fm, width, max_lines):
    """名前を width に収まる行に割る。単語の切れ目が無ければ文字の途中でも割る。

    max_lines を超える分は最終行の真ん中を省略する（一覧と同じく拡張子を残すため）。
    """
    lines, rest = [], text
    while rest and len(lines) < max_lines:
        if fm.horizontalAdvance(rest) <= width:
            lines.append(rest)
            rest = ""
            break
        if len(lines) == max_lines - 1:
            lines.append(fm.elidedText(rest, Qt.TextElideMode.ElideMiddle, width))
            rest = ""
            break
        # 入る最長の頭を探し、その中で最後の切れ目があればそこで割る
        n = 1
        while n < len(rest) and fm.horizontalAdvance(rest[:n + 1]) <= width:
            n += 1
        cut = max((i + 1 for i in range(n) if rest[i] in _BREAK_AFTER), default=0)
        cut = cut if cut > n // 2 else n
        lines.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    return lines


class IconNameDelegate(NameEditDelegate):
    """アイコン表示の名前を折り返して描く。省略しない（行数の上限を超えた分だけ省略）。

    描画そのものは Qt に任せ、渡す文字列に改行を入れるだけにする。
    選択色などはスタイルシートがそのまま効く。
    """

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        view = self.parent()
        width = view.gridSize().width() - theme.ICON_TEXT_MARGIN
        lines = wrap_name(option.text, option.fontMetrics, width, view.text_lines)
        option.text = "\n".join(lines)

    def sizeHint(self, option, index):
        view = self.parent()
        grid = view.gridSize()
        return QSize(grid.width() - theme.ICON_SPACING * 2, grid.height() - theme.ICON_SPACING * 2)


class FileView(QTreeView):
    """列つきの一覧。Explorer の詳細表示に相当する。"""

    def __init__(self, on_activate, on_back, on_middle=None,
                 on_drop=None, on_hover=None, parent=None):
        super().__init__(parent)
        self._on_activate = on_activate
        self._on_back = on_back
        self._on_middle = on_middle
        self._on_drop = on_drop
        self._on_hover = on_hover

        self.setObjectName("FileList")
        self.setRootIsDecorated(False)      # ツリーの三角を出さない＝ただの一覧にする
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSortingEnabled(False)       # 並び替えは自前で持つので Qt には任せない
        self.setAllColumnsShowFocus(True)
        # 末尾ではなく真ん中を省略する。
        # ファイル名は頭が同じで末尾で枝分かれすることが多く（_v2, _PANEL, 日付など）、
        # 末尾を削ると区別がつかなくなる。拡張子も常に見えるようにしておく。
        self.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        # 編集は F2 と右クリックからだけ。うっかりクリックで名前が変わると事故になる。
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setItemDelegateForColumn(COL_NAME, NameEditDelegate(self))
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        _setup_dnd(self)
        self.doubleClicked.connect(lambda idx: self._on_activate(idx.row()))

        header = self.header()
        header.setSectionsClickable(True)
        header.setStretchLastSection(False)
        header.setHighlightSections(False)

    def apply_metrics(self):
        header = self.header()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(60)

        # サイズと更新日時は中身の幅が決まっているので固定する。
        # 名前だけ余りを全部もらう。窓の幅を変えても自動で追従する。
        header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        for col, width in (
            (COL_SIZE, theme.COL_SIZE_WIDTH),
            (COL_TYPE, theme.COL_TYPE_WIDTH),
            (COL_DATE, theme.COL_DATE_WIDTH),
            (COL_ATTR, theme.COL_ATTR_WIDTH),
        ):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            self.setColumnWidth(col, width)
        self.setIndentation(0)

    def keyPressEvent(self, event):
        if _handled(self, event, self._on_activate, self._on_back):
            return
        super().keyPressEvent(event)

    def mouseReleaseEvent(self, event):
        if _middle_handled(self, event, self._on_middle):
            return
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event):
        _dnd_enter(self, event, self._on_hover)

    def dragMoveEvent(self, event):
        _dnd_enter(self, event, self._on_hover)

    def dropEvent(self, event):
        _dnd_drop(self, event, self._on_drop)


class IconView(QListView):
    """アイコン表示。同じモデルの 0 列目だけを並べる。"""

    icon_size_changed = Signal(int)

    def __init__(self, on_activate, on_back, on_middle=None,
                 on_drop=None, on_hover=None, parent=None):
        super().__init__(parent)
        self._on_activate = on_activate
        self._on_back = on_back
        self._on_middle = on_middle
        self._on_drop = on_drop
        self._on_hover = on_hover
        self._size_step = theme.ICON_SIZES.index(theme.ICON_SIZE_DEFAULT)

        self.setObjectName("IconList")
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)   # 並べ替えられて散らからないように
        self.setUniformItemSizes(True)
        # 名前は省略せず折り返す。升目の高さは、今のフォルダで一番長い名前に合わせる
        # （上限 theme.ICON_TEXT_MAX_LINES 行）。改行は IconNameDelegate が入れる。
        # 折り返しを有効にしておかないと、Qt が一行ぶんの高さしか取らず改行ごと省略する。
        self.setWordWrap(True)
        self.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.setSpacing(theme.ICON_SPACING)
        self.text_lines = 1
        self._apply_icon_size()
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setItemDelegate(IconNameDelegate(self))
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        _setup_dnd(self)
        self.doubleClicked.connect(lambda idx: self._on_activate(idx.row()))

    def keyPressEvent(self, event):
        if _handled(self, event, self._on_activate, self._on_back):
            return
        super().keyPressEvent(event)

    def mouseReleaseEvent(self, event):
        if _middle_handled(self, event, self._on_middle):
            return
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event):
        _dnd_enter(self, event, self._on_hover)

    def dragMoveEvent(self, event):
        _dnd_enter(self, event, self._on_hover)

    def dropEvent(self, event):
        _dnd_drop(self, event, self._on_drop)

    def wheelEvent(self, event):
        """Ctrl+ホイールで大きさを変える。Chrome の拡大縮小と同じ手つき。"""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            step = 1 if event.angleDelta().y() > 0 else -1
            self.step_icon_size(step)
            event.accept()
            return
        super().wheelEvent(event)

    def size_step(self):
        return self._size_step

    def set_size_step(self, step):
        """段を直接指定する（状態の復元用）。範囲外は端に丸める。"""
        step = max(0, min(len(theme.ICON_SIZES) - 1, step))
        if step != self._size_step:
            self._size_step = step
            self._apply_icon_size()
            self.icon_size_changed.emit(theme.ICON_SIZES[step])

    def step_icon_size(self, step):
        new = max(0, min(len(theme.ICON_SIZES) - 1, self._size_step + step))
        if new == self._size_step:
            return
        self._size_step = new
        self._apply_icon_size()
        self.icon_size_changed.emit(theme.ICON_SIZES[new])

    def setModel(self, model):
        super().setModel(model)
        for sig in (model.modelReset, model.layoutChanged, model.rowsInserted, model.rowsRemoved):
            sig.connect(self._apply_icon_size)

    def _apply_icon_size(self, *_):
        size = theme.ICON_SIZES[self._size_step]
        self.setIconSize(QSize(size, size))
        # 升目はアイコンに余白を足したもの。詰め具合は theme.py の ICON_PAD_* で決まる。
        # 名前が折り返す分だけ、行の高さを足す。
        width = max(size + theme.ICON_PAD_X, theme.ICON_CELL_MIN_WIDTH)
        fm = self.fontMetrics()
        need = 1
        model = self.model()
        if model is not None:
            text_w = width - theme.ICON_TEXT_MARGIN
            for row in range(model.rowCount()):
                name = model.index(row, 0).data(Qt.ItemDataRole.DisplayRole) or ""
                if fm.horizontalAdvance(name) > text_w:
                    need = max(need, len(wrap_name(name, fm, text_w, theme.ICON_TEXT_MAX_LINES)))
                    if need >= theme.ICON_TEXT_MAX_LINES:
                        break
        self.text_lines = need
        height = size + theme.ICON_PAD_Y
        if need > 1 and model is not None and model.rowCount():
            # 文字欄の高さを Qt に実測させ、need 行ぶんに足りない分だけ升目を伸ばす。
            # 足りないと Qt が最後に入る行で残りをまとめて省略してしまう。
            height += max(0, need * fm.lineSpacing() - self._text_height(width, height))
        grid = QSize(width, height)
        if grid != self.gridSize():
            self.setGridSize(grid)
        self.viewport().update()

    def _text_height(self, width, height):
        """升目が width x height のとき、Qt が名前に割り当てる高さ。"""
        opt = QStyleOptionViewItem()
        opt.initFrom(self)
        opt.rect = QRect(0, 0, width - theme.ICON_SPACING * 2, height - theme.ICON_SPACING * 2)
        opt.decorationSize = self.iconSize()
        opt.decorationPosition = QStyleOptionViewItem.Position.Top
        opt.displayAlignment = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
        opt.features = QStyleOptionViewItem.ViewItemFeature.HasDisplay \
            | QStyleOptionViewItem.ViewItemFeature.HasDecoration \
            | QStyleOptionViewItem.ViewItemFeature.WrapText
        opt.text = "x"
        opt.icon = self.model().index(0, 0).data(Qt.ItemDataRole.DecorationRole) or opt.icon
        return self.style().subElementRect(QStyle.SubElement.SE_ItemViewItemText, opt, self).height()


def _setup_dnd(widget):
    """一覧・アイコン共通のドラッグ設定。

    既定は移動。Windows の「同じドライブなら移動、別なら複製」という
    見えない分岐は持ち込まない。Ctrl を押したときだけ複製にする。
    """
    widget.setDragEnabled(True)
    widget.setAcceptDrops(True)
    widget.setDropIndicatorShown(True)
    widget.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
    widget.setDefaultDropAction(Qt.DropAction.MoveAction)


def _drop_paths(mime):
    return [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]


def _dnd_enter(widget, event, on_hover):
    if not event.mimeData().hasUrls():
        event.ignore()
        return
    copy = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
    row = widget.indexAt(event.position().toPoint()).row()
    if on_hover:
        on_hover(row, copy)
    event.setDropAction(
        Qt.DropAction.CopyAction if copy else Qt.DropAction.MoveAction
    )
    event.accept()


def _dnd_drop(widget, event, on_drop):
    paths = _drop_paths(event.mimeData())
    if not paths or not on_drop:
        event.ignore()
        return
    copy = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
    row = widget.indexAt(event.position().toPoint()).row()
    event.setDropAction(
        Qt.DropAction.CopyAction if copy else Qt.DropAction.MoveAction
    )
    event.accept()
    on_drop(paths, row, copy)


def _middle_handled(widget, event, on_middle) -> bool:
    """中クリックで新しいタブ。ブラウザと同じ手つき。"""
    if event.button() != Qt.MouseButton.MiddleButton or on_middle is None:
        return False
    idx = widget.indexAt(event.position().toPoint())
    if not idx.isValid():
        return False
    on_middle(idx.row())
    return True


def _handled(widget, event, on_activate, on_back) -> bool:
    """Enter で開く / Backspace で上へ。両ビューで挙動を同じにするため共有する。"""
    key = event.key()
    if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
        idx = widget.currentIndex()
        if idx.isValid():
            on_activate(idx.row())
        return True
    if key == Qt.Key.Key_Backspace:
        on_back()
        return True
    return False
