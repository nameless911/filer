"""ファイルを変更する操作。判断と検証はここに集める。

方針:
  - 上書きは絶対にしない。既に在るなら断る。
  - 失敗は例外ではなく理由の文字列で返す。呼び出し側がそのまま表示できる。
  - OS 呼び出しは osops.py、並び順や列挙は model.py。ここは混ぜない。
"""

import os

from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtWidgets import QApplication

# --- クリップボード ---------------------------------------------------------
# Windows では次の2つが揃って初めて「ファイルのコピー／切り取り」になる。
#   CF_HDROP              … パスの一覧（Qt では urls として見える）
#   Preferred DropEffect  … 4バイト。2ならコピー、1なら移動。
# つまり Ctrl+C と Ctrl+X の違いは、この4バイトだけ。
# 切り取っても、この時点では何も消えない。消すのは貼り付け側の仕事。

DROPEFFECT_MOVE = 1
DROPEFFECT_COPY = 2
DROP_FORMAT = "Preferred DropEffect"


def put_clipboard(paths, move=False):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
    effect = DROPEFFECT_MOVE if move else DROPEFFECT_COPY
    mime.setData(DROP_FORMAT, effect.to_bytes(4, "little"))
    # テキストとしても貼れるようにしておく。エディタ等に投げるとき便利。
    mime.setText("\n".join(paths))
    QApplication.clipboard().setMimeData(mime)


def read_clipboard():
    """(パス一覧, 移動かどうか) を返す。ファイルが無ければ ([], False)。"""
    mime = QApplication.clipboard().mimeData()
    if not mime.hasUrls():
        return [], False
    paths = [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]
    raw = bytes(mime.data(DROP_FORMAT))
    move = bool(raw) and int.from_bytes(raw[:4], "little") == DROPEFFECT_MOVE
    return paths, move


def clear_clipboard():
    """移動の貼り付けが済んだら空にする。放置すると二重に移動しようとする。"""
    QApplication.clipboard().clear()

# Windows でファイル名に使えない文字。Linux でも弾いておく（可搬性のため）。
INVALID_CHARS = set('\\/:*?"<>|')

# Windows の予約名。拡張子を付けても使えない。
RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def validate_name(name):
    """使える名前かを調べる。問題なければ None、駄目なら理由を返す。"""
    name = name.strip()
    if not name:
        return "名前が空です"
    if name in (".", ".."):
        return "その名前は使えません"
    bad = sorted(set(name) & INVALID_CHARS)
    if bad:
        return "使えない文字が含まれています: " + " ".join(bad)
    if os.path.splitext(name)[0].upper() in RESERVED:
        return f"{name} は予約された名前です"
    if name[-1] in " .":
        return "末尾の空白とピリオドは使えません"
    if len(name) > 255:
        return "名前が長すぎます"
    return None


def rename(path, new_name):
    """名前を変える。成功したら (新しいパス, None)、失敗したら (None, 理由)。"""
    reason = validate_name(new_name)
    if reason:
        return None, reason

    new_name = new_name.strip()
    folder = os.path.dirname(path)
    target = os.path.join(folder, new_name)

    if os.path.normcase(target) == os.path.normcase(path):
        return path, None  # 変わっていないので何もしない

    # 大文字小文字だけの変更は、同じ物を指すので衝突扱いにしない
    same_file_different_case = os.path.normcase(target) == os.path.normcase(path)
    if os.path.exists(target) and not same_file_different_case:
        return None, f"{new_name} は既に存在します"

    try:
        os.rename(path, target)
    except OSError as e:
        return None, e.strerror or str(e)
    return target, None
