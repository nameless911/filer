"""タイトルバーを自前で描くための Windows 固有処理。

素朴に FramelessWindowHint だけ付けると、スナップ・リサイズ・影・最大化の
アニメーションが全部死ぬ。それらは Windows 側の仕事なので、
「枠のスタイルは残したまま、枠の描画だけ消す」という形にする。

手順:
  1. WS_THICKFRAME 等を残す  → スナップとリサイズの機能が生きる
  2. WM_NCCALCSIZE を握りつぶす → 枠が描かれなくなり、全面がこちらの領域になる
  3. WM_NCHITTEST に自分で答える → どこを掴んだら移動か、どこが端かを教える

非 Windows では何もしない（通常の枠のまま動く）。
"""

import ctypes
import sys
from ctypes import wintypes

IS_WINDOWS = sys.platform.startswith("win")

WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084

# ヒットテストの戻り値
HTCLIENT = 1
HTCAPTION = 2
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17

GWL_STYLE = -16
WS_POPUP = 0x80000000
WS_THICKFRAME = 0x00040000      # これが無いとリサイズとスナップが効かない
WS_CAPTION = 0x00C00000         # これが無いと最大化アニメーションが効かない
WS_SYSMENU = 0x00080000
WS_MAXIMIZEBOX = 0x00010000
WS_MINIMIZEBOX = 0x00020000

SM_CXSIZEFRAME = 32
SM_CYSIZEFRAME = 33
SM_CXPADDEDBORDER = 92

SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOOWNERZORDER = 0x0200
SWP_FRAMECHANGED = 0x0020  # これを送らないとスタイル変更が反映されず、窓が出ない

BORDER = 6  # 端をつかめる幅(px)


class MARGINS(ctypes.Structure):
    _fields_ = [
        ("cxLeftWidth", ctypes.c_int),
        ("cxRightWidth", ctypes.c_int),
        ("cyTopHeight", ctypes.c_int),
        ("cyBottomHeight", ctypes.c_int),
    ]


def apply(window) -> bool:
    """ウィンドウを枠なしにする。成功したら True。

    window は caption_hit(global_point) -> bool を持っていること。
    """
    if not IS_WINDOWS:
        return False
    try:
        hwnd = int(window.winId())
        user32 = ctypes.windll.user32
        dwm = ctypes.windll.dwmapi

        get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
        set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
        get_long.restype = ctypes.c_ssize_t
        get_long.argtypes = [wintypes.HWND, ctypes.c_int]
        set_long.restype = ctypes.c_ssize_t
        set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]

        # 丸ごと上書きすると WS_VISIBLE まで消えて、窓が永久に出てこなくなる。
        # 今のスタイルに、必要なビットを足すだけにすること。
        style = get_long(hwnd, GWL_STYLE)
        style |= WS_THICKFRAME | WS_CAPTION | WS_SYSMENU | WS_MAXIMIZEBOX | WS_MINIMIZEBOX
        set_long(hwnd, GWL_STYLE, style)

        # スタイルを変えただけでは反映されない。枠が変わったと明示的に伝える。
        user32.SetWindowPos(
            hwnd, 0, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOOWNERZORDER | SWP_FRAMECHANGED,
        )

        # 影を残す。1px だけ伸ばせば DWM が描いてくれる。
        margins = MARGINS(0, 0, 1, 0)
        dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
        return True
    except (OSError, AttributeError, ValueError):
        return False


def handle(window, message):
    """nativeEvent から呼ぶ。処理したら (True, 戻り値)、しなければ (False, 0)。"""
    msg = wintypes.MSG.from_address(int(message))

    if msg.message == WM_NCCALCSIZE and msg.wParam:
        # 最大化中は枠の分だけ削らないと、画面外にはみ出して端が切れる
        if window.isMaximized():
            user32 = ctypes.windll.user32
            pad = user32.GetSystemMetrics(SM_CXPADDEDBORDER)
            cx = user32.GetSystemMetrics(SM_CXSIZEFRAME) + pad
            cy = user32.GetSystemMetrics(SM_CYSIZEFRAME) + pad
            rect = wintypes.RECT.from_address(msg.lParam)
            rect.left += cx
            rect.top += cy
            rect.right -= cx
            rect.bottom -= cy
        return True, 0

    if msg.message == WM_NCHITTEST:
        # lParam の下位/上位 16bit が画面座標。符号付きで取り出す。
        x = ctypes.c_short(msg.lParam & 0xFFFF).value
        y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
        return True, _hit(window, x, y)

    return False, 0


def _hit(window, gx, gy):
    geo = window.frameGeometry()
    if not window.isMaximized():
        left = gx < geo.left() + BORDER
        right = gx > geo.right() - BORDER
        top = gy < geo.top() + BORDER
        bottom = gy > geo.bottom() - BORDER
        if top and left:
            return HTTOPLEFT
        if top and right:
            return HTTOPRIGHT
        if bottom and left:
            return HTBOTTOMLEFT
        if bottom and right:
            return HTBOTTOMRIGHT
        if left:
            return HTLEFT
        if right:
            return HTRIGHT
        if top:
            return HTTOP
        if bottom:
            return HTBOTTOM

    # 掴んで動かせる場所か、ウィンドウ側に聞く
    if window.caption_hit(gx, gy):
        return HTCAPTION
    return HTCLIENT
