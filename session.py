"""開いている窓とタブの状態を、ファイルに書いて読むだけ。Qt に依存しない。

何を覚えるか（窓の位置・タブ・履歴・表示モード等）は main.py が決める。
ここは受け取った辞書をそのまま JSON にして、壊れない書き方で置くだけ。
"""

import json
import os
import tempfile

VERSION = 1
HISTORY_LIMIT = 50   # タブごとに覚えておく戻る/進むの件数。増やしても困らないが、際限なく溜めない。


def default_path():
    """いつもの保存先。%APPDATA%\\Filer\\session.json（無ければホーム直下）。"""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Filer", "session.json")


def temp_path():
    """再起動の受け渡し用。いつもの保存先とは分けて、複数の窓の取り違えを防ぐ。"""
    fd, path = tempfile.mkstemp(prefix="filer-restart-", suffix=".json")
    os.close(fd)
    return path


def save(windows, path=None):
    """windows は main.py が作った窓ごとの辞書の並び。書き込みは置き換えで一瞬に行う。

    途中で落ちても、前の中身か新しい中身のどちらかが残る（半端な JSON を残さない）。
    """
    path = path or default_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {"version": VERSION, "windows": windows}
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def load(path=None, remove=False):
    """保存された窓の並びを返す。無い・壊れている・版が違うなら空の並び。"""
    path = path or default_path()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    finally:
        if remove:
            try:
                os.remove(path)
            except OSError:
                pass
    if not isinstance(data, dict) or data.get("version") != VERSION:
        return []
    windows = data.get("windows")
    return windows if isinstance(windows, list) else []


def existing_dir(path):
    """消えたフォルダは、残っている一番近い親に読み替える。全部無ければホーム。

    USB を抜いた後や、フォルダを消した後でも、復元で開けないまま止まらないように。
    """
    path = os.path.abspath(path or os.path.expanduser("~"))
    while path and not os.path.isdir(path):
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return path if path and os.path.isdir(path) else os.path.expanduser("~")
