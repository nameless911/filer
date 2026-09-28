"""OS に直接お願いする操作だけを集める。ここが移植時の差し替え点になる。

判断（可否や検証）は書かない。呼ぶだけ。
"""

import ctypes
import os
import shutil
import subprocess
import sys
from ctypes import wintypes

IS_WINDOWS = sys.platform.startswith("win")

# --- SHFileOperation --------------------------------------------------------
# コピーと移動の中身は自分で書かない。OS に任せると次が全部ついてくる。
#   進捗ダイアログ / 衝突時の問い合わせ / Ctrl+Z での取り消し / 昇格(UAC) /
#   長いパス・ジャンクション・属性の正しい扱い
# ここを自作すると、失敗したときの被害がファイルの消失になる。

FO_MOVE, FO_COPY, FO_DELETE = 1, 2, 3
FOF_ALLOWUNDO = 0x0040        # 取り消せるようにする。削除ならゴミ箱行きになる。
FOF_NOCONFIRMMKDIR = 0x0200   # フォルダ作成の確認だけは省く


class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", ctypes.c_uint16),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


def _packed(paths):
    """SHFileOperation はヌル区切り＋末尾二重ヌルの文字列を要求する。"""
    return "\0".join(os.path.normpath(p) for p in paths) + "\0\0"


def _shell_op(func, sources, dest=None, hwnd=0):
    op = SHFILEOPSTRUCTW()
    op.hwnd = hwnd
    op.wFunc = func
    op.pFrom = _packed(sources)
    op.pTo = _packed([dest]) if dest else None
    op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMMKDIR
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if op.fAnyOperationsAborted:
        return "中止しました"
    if result != 0:
        return f"失敗しました (コード {result})"
    return None


def copy_files(sources, dest_dir, hwnd=0):
    """成功したら None、駄目なら理由を返す。"""
    if IS_WINDOWS:
        return _shell_op(FO_COPY, sources, dest_dir, hwnd)
    return _fallback(sources, dest_dir, move=False)


def move_files(sources, dest_dir, hwnd=0):
    if IS_WINDOWS:
        return _shell_op(FO_MOVE, sources, dest_dir, hwnd)
    return _fallback(sources, dest_dir, move=True)


def delete_files(paths, hwnd=0):
    """ゴミ箱へ送る。完全削除はここでは行わない。"""
    if IS_WINDOWS:
        return _shell_op(FO_DELETE, paths, None, hwnd)
    return "この環境では未実装です"


def _fallback(sources, dest_dir, move):
    """Windows 以外。衝突は上書きせず断る。"""
    for src in sources:
        target = os.path.join(dest_dir, os.path.basename(src))
        if os.path.exists(target):
            return f"{os.path.basename(src)} は既に存在します"
        try:
            if move:
                shutil.move(src, target)
            elif os.path.isdir(src):
                shutil.copytree(src, target)
            else:
                shutil.copy2(src, target)
        except OSError as e:
            return e.strerror or str(e)
    return None


def open_path(path):
    """既定のアプリで開く。フォルダなら OS のファイラーが開く。"""
    if IS_WINDOWS:
        os.startfile(path)  # noqa: S606 - 既定の関連付けに委ねる
        return
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen([opener, path])


class SHFILEINFOW(ctypes.Structure):
    _fields_ = [
        ("hIcon", wintypes.HANDLE),
        ("iIcon", ctypes.c_int),
        ("dwAttributes", wintypes.DWORD),
        ("szDisplayName", ctypes.c_wchar * 260),
        ("szTypeName", ctypes.c_wchar * 80),
    ]


SHGFI_TYPENAME = 0x000000400
SHGFI_USEFILEATTRIBUTES = 0x000000010  # 実ファイルに触らず拡張子だけで解決する
FILE_ATTRIBUTE_NORMAL = 0x00000080
FILE_ATTRIBUTE_DIRECTORY = 0x00000010


def type_name(path, is_dir=False):
    """「PDF ファイル」等の種類名。Explorer の「種類」列と同じ出所。

    SHGFI_USEFILEATTRIBUTES を付けるのでディスクにも行かない。
    クラウドのプレースホルダを実体化させる心配がない。
    """
    if not IS_WINDOWS:
        return ""
    info = SHFILEINFOW()
    attrs = FILE_ATTRIBUTE_DIRECTORY if is_dir else FILE_ATTRIBUTE_NORMAL
    ok = ctypes.windll.shell32.SHGetFileInfoW(
        os.path.normpath(path),
        attrs,
        ctypes.byref(info),
        ctypes.sizeof(info),
        SHGFI_TYPENAME | SHGFI_USEFILEATTRIBUTES,
    )
    return info.szTypeName if ok else ""


class SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", wintypes.ULONG),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hIcon", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


SEE_MASK_INVOKEIDLIST = 0x0000000C  # これが無いと properties 動詞が効かない
SW_SHOW = 5


def properties(path, hwnd=0):
    """Windows 標準のプロパティダイアログを出す。自前では作らない。"""
    if not IS_WINDOWS:
        return "この環境では未実装です"
    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = SEE_MASK_INVOKEIDLIST
    info.hwnd = hwnd
    info.lpVerb = "properties"
    info.lpFile = os.path.normpath(path)
    info.nShow = SW_SHOW
    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)):
        return "プロパティを開けません"
    return None


# --- ディスク情報 ------------------------------------------------------------

_BUS_NAMES = {
    1: "SCSI", 3: "ATA", 4: "IEEE1394", 7: "USB",
    10: "SAS", 11: "SATA", 12: "SD", 13: "MMC", 17: "NVMe",
}
_IOCTL_STORAGE_QUERY = 0x002D1400


def disk_info(drive: str) -> dict:
    """容量・空き・バス種別・デバイス名を返す。失敗した項目は空 / -1。"""
    result = {"free": -1, "total": -1, "bus": "", "device": ""}
    try:
        u = shutil.disk_usage(drive)
        result["free"] = u.free
        result["total"] = u.total
    except OSError:
        pass
    if not IS_WINDOWS:
        return result
    try:
        root = drive.rstrip("\\/")
        h = ctypes.windll.kernel32.CreateFileW(
            f"\\\\.\\{root}", 0,
            0x00000001 | 0x00000002,   # FILE_SHARE_READ | FILE_SHARE_WRITE
            None, 3, 0, None           # OPEN_EXISTING
        )
        if h in (0, ctypes.c_void_p(-1).value):
            return result
        try:
            q = (ctypes.c_uint32 * 3)(0, 0, 0)   # StorageDeviceProperty / StandardQuery
            buf = (ctypes.c_uint8 * 512)()
            ret = ctypes.c_ulong(0)
            ok = ctypes.windll.kernel32.DeviceIoControl(
                h, _IOCTL_STORAGE_QUERY,
                q, 8, buf, 512, ctypes.byref(ret), None
            )
            if ok and ret.value >= 36:
                raw = bytes(buf[:ret.value])
                result["bus"] = _BUS_NAMES.get(
                    int.from_bytes(raw[28:32], "little"), ""
                )
                def _cstr(off):
                    if not off or off >= len(raw):
                        return ""
                    end = raw.find(0, off)
                    return raw[off: end if end >= 0 else len(raw)].decode(
                        "ascii", errors="ignore"
                    ).strip()
                vendor  = _cstr(int.from_bytes(raw[12:16], "little"))
                product = _cstr(int.from_bytes(raw[16:20], "little"))
                result["device"] = (f"{vendor} {product}".strip()
                                    if vendor else product)
        finally:
            ctypes.windll.kernel32.CloseHandle(h)
    except Exception:
        pass
    return result


