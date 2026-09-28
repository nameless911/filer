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


# --- 取り外し ----------------------------------------------------------------
# 「ハードウェアの安全な取り外し」と同じ経路（CM_Request_Device_Eject）を使う。
# 開いているアプリへの問い合わせ・キャッシュの書き出し・拒否理由の取得は OS がやる。
# ボリュームのロックやマウント解除を自前でやると、拒否されるべき場面で無理に外してしまう。

_IOCTL_STORAGE_GET_DEVICE_NUMBER = 0x002D1080
_DIGCF_PRESENT, _DIGCF_DEVICEINTERFACE = 0x02, 0x10
_INVALID_HANDLE = ctypes.c_void_p(-1).value

_VETO_REASONS = {
    1: "古い形式のデバイスが拒否しました",
    2: "閉じる処理が終わっていません",
    3: "アプリが使用中です",
    4: "サービスが使用中です",
    5: "ファイルを開いているアプリがあります",
    6: "デバイスが拒否しました",
    7: "ドライバーが拒否しました",
    8: "このデバイスは取り外しに対応していません",
    9: "電源が足りません",
    10: "無効にできないデバイスです",
    11: "古い形式のドライバーが拒否しました",
    12: "権限が足りません",
}


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


class _SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("InterfaceClassGuid", _GUID),
                ("Flags", wintypes.DWORD), ("Reserved", ctypes.c_size_t)]


class _SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("ClassGuid", _GUID),
                ("DevInst", wintypes.DWORD), ("Reserved", ctypes.c_size_t)]


# GUID_DEVINTERFACE_DISK {53F56307-B6BF-11D0-94F2-00A0C91EFB8B}
_GUID_DISK = _GUID(0x53F56307, 0xB6BF, 0x11D0,
                   (ctypes.c_ubyte * 8)(0x94, 0xF2, 0x00, 0xA0, 0xC9, 0x1E, 0xFB, 0x8B))


def _k32():
    """戻り値の型を設定した専用の kernel32。共有の windll.kernel32 は書き換えない。"""
    k32 = ctypes.WinDLL("kernel32")
    k32.CreateFileW.restype = wintypes.HANDLE
    return k32


def _device_number(path):
    """ボリュームやディスクのパスから (種別, ディスク番号) を返す。取れなければ None。"""
    k32 = _k32()
    h = k32.CreateFileW(path, 0, 0x1 | 0x2, None, 3, 0, None)
    if not h or h == _INVALID_HANDLE:
        return None
    try:
        out = (wintypes.DWORD * 3)()
        ret = wintypes.DWORD()
        if not k32.DeviceIoControl(wintypes.HANDLE(h), _IOCTL_STORAGE_GET_DEVICE_NUMBER,
                                   None, 0, out, ctypes.sizeof(out), ctypes.byref(ret), None):
            return None
        return out[0], out[1]
    finally:
        k32.CloseHandle(wintypes.HANDLE(h))


def _disk_devinst(number):
    """ディスク番号に対応するデバイスノードを探す。"""
    sa = ctypes.windll.setupapi
    sa.SetupDiGetClassDevsW.restype = ctypes.c_void_p
    sa.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(_GUID), wintypes.LPCWSTR,
                                        wintypes.HWND, wintypes.DWORD]
    sa.SetupDiEnumDeviceInterfaces.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                               ctypes.POINTER(_GUID), wintypes.DWORD,
                                               ctypes.POINTER(_SP_DEVICE_INTERFACE_DATA)]
    sa.SetupDiGetDeviceInterfaceDetailW.argtypes = [ctypes.c_void_p,
                                                    ctypes.POINTER(_SP_DEVICE_INTERFACE_DATA),
                                                    ctypes.c_void_p, wintypes.DWORD,
                                                    ctypes.POINTER(wintypes.DWORD),
                                                    ctypes.POINTER(_SP_DEVINFO_DATA)]
    sa.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]

    hdev = sa.SetupDiGetClassDevsW(ctypes.byref(_GUID_DISK), None, None,
                                   _DIGCF_PRESENT | _DIGCF_DEVICEINTERFACE)
    if not hdev or hdev == _INVALID_HANDLE:
        return None
    try:
        i = 0
        while True:
            iface = _SP_DEVICE_INTERFACE_DATA(cbSize=ctypes.sizeof(_SP_DEVICE_INTERFACE_DATA))
            if not sa.SetupDiEnumDeviceInterfaces(hdev, None, ctypes.byref(_GUID_DISK),
                                                  i, ctypes.byref(iface)):
                return None
            i += 1
            need = wintypes.DWORD()
            sa.SetupDiGetDeviceInterfaceDetailW(hdev, ctypes.byref(iface), None, 0,
                                                ctypes.byref(need), None)
            buf = ctypes.create_string_buffer(need.value)
            # SP_DEVICE_INTERFACE_DETAIL_DATA_W の cbSize は 64bit で 8、32bit で 6
            ctypes.c_uint32.from_buffer(buf).value = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
            info = _SP_DEVINFO_DATA(cbSize=ctypes.sizeof(_SP_DEVINFO_DATA))
            if not sa.SetupDiGetDeviceInterfaceDetailW(hdev, ctypes.byref(iface), buf,
                                                       need, None, ctypes.byref(info)):
                continue
            path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
            num = _device_number(path)
            if num and num[1] == number:
                return info.DevInst
    finally:
        sa.SetupDiDestroyDeviceInfoList(hdev)


def eject_drive(drive: str):
    """ドライブを取り外せる状態にする。成功したら None、駄目なら理由を返す。"""
    if not IS_WINDOWS:
        return "この環境では未実装です"
    root = drive.rstrip("\\/")
    num = _device_number(f"\\\\.\\{root}")
    if num is None:
        return "ドライブの情報を取れません"
    devinst = _disk_devinst(num[1])
    if devinst is None:
        return "ドライブに対応するデバイスが見つかりません"

    cfg = ctypes.windll.cfgmgr32
    # ディスクそのものではなく、その親（USB 大容量記憶装置など）を外す。
    # 外せない親なら一段ずつ上をたどる。
    parent = wintypes.DWORD()
    if cfg.CM_Get_Parent(ctypes.byref(parent), wintypes.DWORD(devinst), 0) != 0:
        return "親デバイスが見つかりません"
    veto_type = ctypes.c_int(0)
    veto_name = ctypes.create_unicode_buffer(260)
    for _ in range(3):   # 一時的に拒否されることがあるので少しだけ再試行する
        rc = cfg.CM_Request_Device_EjectW(parent, ctypes.byref(veto_type),
                                          veto_name, len(veto_name), 0)
        if rc == 0 and veto_type.value == 0:
            return None
    reason = _VETO_REASONS.get(veto_type.value, f"取り外せません (コード {rc})")
    who = veto_name.value
    return f"{reason}: {who}" if who else reason


