"""ファイル一覧の挙動そのもの。Qt に依存しないので単体で動かして確かめられる。

ここを読めば「なぜそう並ぶか」「なぜそう表示されるか」が全部わかる状態を保つこと。
便利だが中身の追えない部品（QFileSystemModel 等）は意図的に使わない。
"""

import os
import re
import sys
from dataclasses import dataclass

# --- OneDrive 等のプレースホルダ判定用（Windows のファイル属性ビット） -------
# これらが立っているファイルは実体がローカルに無い。中身に触ると同期が走るので触らない。
FILE_ATTRIBUTE_OFFLINE = 0x00001000
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x00040000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000
FILE_ATTRIBUTE_READONLY = 0x00000001
FILE_ATTRIBUTE_HIDDEN = 0x00000002
FILE_ATTRIBUTE_SYSTEM = 0x00000004
FILE_ATTRIBUTE_ARCHIVE = 0x00000020
FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
FILE_ATTRIBUTE_COMPRESSED = 0x00000800
FILE_ATTRIBUTE_ENCRYPTED = 0x00004000

_PLACEHOLDER_MASK = (
    FILE_ATTRIBUTE_OFFLINE
    | FILE_ATTRIBUTE_RECALL_ON_OPEN
    | FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS
)


@dataclass(slots=True)
class Entry:
    """一覧の1行。表示に必要なものだけを持つ。"""

    name: str
    path: str
    is_dir: bool
    size: int          # ディレクトリは -1（サイズを数えに行かない）
    mtime: float
    hidden: bool
    placeholder: bool  # 実体がローカルに無い（OneDrive 等）
    attrs: int = 0     # Windows のファイル属性ビット。表示は attr_letters() で。

    @property
    def ext(self) -> str:
        if self.is_dir:
            return ""
        return os.path.splitext(self.name)[1].lower()


# --- 並び順 -----------------------------------------------------------------
# Explorer は "2" < "10" のように数字を数値として比較する（自然順）。
# ここが違うと一瞬で「別物」だとバレるので、最初から合わせる。

_DIGITS = re.compile(r"(\d+)")


def natural_key(name: str):
    """'panel_v2.png' < 'panel_v10.png' になるキーを作る。"""
    parts = _DIGITS.split(name.lower())
    # split の結果は [非数字, 数字, 非数字, ...] と交互に並ぶ
    return [int(p) if i % 2 else p for i, p in enumerate(parts)]


def sort_entries(entries, key="name", reverse=False, dirs_first=True):
    """一覧を並べ替える。Explorer 同様フォルダを先に出すのが既定。"""
    if key == "name":
        primary = lambda e: natural_key(e.name)
    elif key == "size":
        primary = lambda e: e.size
    elif key == "mtime":
        primary = lambda e: e.mtime
    elif key == "ext":
        primary = lambda e: (natural_key(e.ext), natural_key(e.name))
    elif key == "attr":
        primary = lambda e: (attr_letters(e.attrs), natural_key(e.name))
    else:
        raise ValueError(f"unknown sort key: {key}")

    if dirs_first:
        # フォルダ/ファイルの別は常に最優先で、昇順降順の影響を受けない
        return sorted(
            sorted(entries, key=primary, reverse=reverse),
            key=lambda e: not e.is_dir,
        )
    return sorted(entries, key=primary, reverse=reverse)


# --- 列挙 -------------------------------------------------------------------


def _attributes(st) -> int:
    return getattr(st, "st_file_attributes", 0)


def list_dir(path, show_hidden=False):
    """1階層ぶんを読む。読めない項目は黙って捨てずに、呼び出し側へ件数で返す。

    戻り値は (entries, skipped) で、skipped は権限等で読めなかった件数。
    """
    entries = []
    skipped = 0

    with os.scandir(path) as it:
        for de in it:
            try:
                # follow_symlinks=False でリンク先を辿らない。
                # 切れたリンクやネットワーク先で固まるのを避ける。
                st = de.stat(follow_symlinks=False)
                is_dir = de.is_dir(follow_symlinks=False)
            except OSError:
                skipped += 1
                continue

            attrs = _attributes(st)
            hidden = bool(attrs & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM))
            if not hidden and de.name.startswith("."):
                hidden = True  # Linux の流儀もそのまま拾う
            if hidden and not show_hidden:
                continue

            entries.append(
                Entry(
                    name=de.name,
                    path=de.path,
                    is_dir=is_dir,
                    size=-1 if is_dir else st.st_size,
                    mtime=st.st_mtime,
                    hidden=hidden,
                    placeholder=bool(attrs & _PLACEHOLDER_MASK),
                    attrs=attrs,
                )
            )

    return entries, skipped


# --- 表示用の整形 -----------------------------------------------------------
# 表示だけの都合。判断ロジックをここに混ぜないこと。

# 属性の表示。attrib コマンドや Explorer の「属性」列と同じ文字を使う。
# 並び順は固定にする（毎回同じ位置に同じ文字が来るほうが目で追いやすい）。
_ATTR_LETTERS = (
    (FILE_ATTRIBUTE_READONLY, "R"),        # 読み取り専用
    (FILE_ATTRIBUTE_ARCHIVE, "A"),         # アーカイブ
    (FILE_ATTRIBUTE_HIDDEN, "H"),          # 隠し
    (FILE_ATTRIBUTE_SYSTEM, "S"),          # システム
    (FILE_ATTRIBUTE_COMPRESSED, "C"),      # 圧縮
    (FILE_ATTRIBUTE_ENCRYPTED, "E"),       # 暗号化
    (FILE_ATTRIBUTE_REPARSE_POINT, "L"),   # ジャンクション/シンボリックリンク
    (FILE_ATTRIBUTE_OFFLINE, "O"),         # 実体がローカルに無い
)


def attr_letters(attrs: int) -> str:
    return "".join(letter for bit, letter in _ATTR_LETTERS if attrs & bit)


_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def format_size(size: int) -> str:
    if size < 0:
        return ""
    if size < 1024:
        return f"{size} B"
    v = float(size)
    for unit in _UNITS[1:]:
        v /= 1024.0
        if v < 1024.0:
            return f"{v:.1f} {unit}" if v < 10 else f"{v:.0f} {unit}"
    return f"{v:.0f} PB"


def format_mtime(ts: float) -> str:
    import datetime

    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    items, skipped = list_dir(target)
    for e in sort_entries(items):
        mark = "/" if e.is_dir else (" [cloud]" if e.placeholder else "")
        print(f"{format_mtime(e.mtime)}  {format_size(e.size):>9}  {e.name}{mark}")
    print(f"\n{len(items)} items" + (f", {skipped} unreadable" if skipped else ""))
