"""アプリのアイコン。コードで描くので画像ファイルを持ち歩かなくてよい。

方針:
  - 16px でも読めること。小さいときは要素を減らす。
  - テーマに追従させない。アイコンは常に同じ顔でいるほうが見つけやすい。
  - 既存のアイコンを模写しない。「探し当てる」という意味だけを借りる。
"""

import random
import struct

from PySide6.QtCore import QBuffer, QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QIcon,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

# クラリスワークス風。柔らかい色の紙が扇状に重なり、角が折れている。
# 90年代の Mac アイコンの作法にならって、輪郭線を一本入れる。
INK = QColor("#4A4640")       # 輪郭
SHEETS = (
    QColor("#A8C8E4"),        # 奥から順に
    QColor("#A9CFA2"),
    QColor("#F2D175"),
    QColor("#F5F1E6"),        # 手前は白い紙
)

SIZES = (16, 20, 24, 32, 48, 64, 128, 256)

# しわくちゃ具合。0 でパリッと新品、3 で鞄の底、4 で破滅。
# 1.0 は使わない（0.5 の次は 2.0 まで飛ぶ）。
CRUMPLE_STEPS = (0.0, 0.5, 2.0, 3.0, 4.0)
CRUMPLE = 0.5
DISASTER = 3.5   # これを超えるとネジやケーブルが生えてくる


def draw(size: int, crumple: float = None) -> QPixmap:
    if crumple is None:
        crumple = CRUMPLE
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    u = size / 100.0          # 100 を基準にした比率で置く
    line = max(1.0, size * 0.032)
    pen = QPen(INK, line, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
               Qt.PenJoinStyle.RoundJoin)

    # 小さいときは枚数を減らす。重ねすぎると潰れて読めない。
    fan = ((-17, 12, -19), (-7, 7, -8), (3, 3, 4), (14, -2, 15))
    if size < 24:
        fan = fan[1::2]

    w, h = 46 * u, 58 * u

    if crumple >= DISASTER and size >= 32:
        _junk(p, u, size, random.Random(7))

    for i, ((dx, dy, rot), color) in enumerate(zip(fan, SHEETS[-len(fan):])):
        rng = random.Random(1000 + i)   # 毎回同じ形になるよう種を固定する
        j = u * (2.2 if size >= 32 else 1.0) * crumple   # 揺らぎの大きさ

        def wob(v):
            return v + rng.uniform(-j, j)

        p.save()
        p.translate((38 + dx) * u, (26 + dy) * u)
        p.rotate(rot)

        fold = (13 + rng.uniform(-3, 5) * crumple) * u   # 折れ方も一枚ずつ変える

        # 縁を少したわませる。直線で結ばず、途中に山を作る。
        path = QPainterPath()
        path.moveTo(wob(0), wob(0))
        path.quadTo(w * 0.5, wob(-2 * u), w - fold, wob(0))        # 上辺
        path.lineTo(wob(w), wob(fold))                              # 折れ角
        path.quadTo(wob(w + 2 * u), h * 0.5, wob(w), wob(h))        # 右辺
        path.quadTo(w * 0.5, wob(h + 2 * u), wob(0), wob(h))        # 下辺
        path.quadTo(wob(-2 * u), h * 0.5, wob(0), wob(0))           # 左辺
        path.closeSubpath()

        p.setPen(pen)
        p.setBrush(color)
        p.drawPath(path)

        if size >= 24:
            # 折り返しの三角
            flap = QPainterPath()
            flap.moveTo(w - fold, wob(0))
            flap.lineTo(wob(w), wob(fold))
            flap.lineTo(w - fold, fold)
            flap.closeSubpath()
            p.setBrush(color.darker(118))
            p.drawPath(flap)

        # クチャッとした折り皺。一番手前の紙にだけ入れる。
        if size >= 48 and crumple > 0.3 and i == len(fan) - 1:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(INK, line * 0.7, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap))
            crease = QPainterPath()
            crease.moveTo(w * 0.18, h * 0.62)
            # しわの本数も増える。くたびれるほど折り目が増える道理。
            for k in range(1, 3 + int(crumple * 2)):
                crease.lineTo(
                    w * (0.18 + 0.16 * k),
                    h * (0.44 if k % 2 else 0.70) + rng.uniform(-3, 3) * u * crumple,
                )
            p.drawPath(crease)

        p.restore()

    p.end()
    return pm



def _junk(p, u, size, rng):
    """破滅級のときだけ生える異物。ネジ、ケーブル、ばね。"""
    cable = QColor("#3A3A3A")
    metal = QColor("#9AA0A6")

    # ケーブル。紙の束の裏から出て、びょいんと跳ねる。
    p.setBrush(Qt.BrushStyle.NoBrush)
    for x0, y0, x1, y1, cx, cy in (
        (18, 46, 2, 14, -14, 66), (78, 40, 98, 18, 108, 58),
    ):
        path = QPainterPath()
        path.moveTo(x0 * u, y0 * u)
        path.cubicTo(cx * u, cy * u, (x1 + 8) * u, (y1 + 24) * u, x1 * u, y1 * u)
        p.setPen(QPen(cable, 3.4 * u, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawPath(path)

    # ばね。等間隔の山を描くだけで、それらしく見える。
    coil = QPainterPath()
    coil.moveTo(66 * u, 84 * u)
    for k in range(6):
        coil.quadTo((70 + k * 5) * u, (76 if k % 2 else 94) * u,
                    (74 + k * 5) * u, 84 * u)
    p.setPen(QPen(metal, 2.6 * u, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawPath(coil)

    # ネジ。頭の溝まで入れる。
    p.setPen(QPen(INK, 1.6 * u))
    for cx, cy, r in ((12, 78, 6), (88, 76, 5), (30, 92, 5)):
        p.setBrush(metal)
        p.drawEllipse(QPointF(cx * u, cy * u), r * u, r * u)
        p.drawLine(QPointF((cx - r * 0.6) * u, cy * u),
                   QPointF((cx + r * 0.6) * u, cy * u))


def icon(crumple: float = None) -> QIcon:
    ico = QIcon()
    for s in SIZES:
        ico.addPixmap(draw(s, crumple))
    return ico


def _png_bytes(size: int) -> bytes:
    # QByteArray は変数に保持すること。一時オブジェクトのままだと解放されて落ちる。
    store = QByteArray()
    buf = QBuffer(store)
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    draw(size).toImage().convertToFormat(QImage.Format.Format_ARGB32).save(buf, "PNG")
    buf.close()
    return bytes(store)


def write_ico(path: str):
    """PyInstaller の --icon に渡す .ico を書き出す。

    Vista 以降は各サイズを PNG のまま収められるので、自前で組み立てる。
    （Qt の ICO 書き出しに頼らずに済む）
    """
    blobs = [(s, _png_bytes(s)) for s in SIZES]
    header = struct.pack("<HHH", 0, 1, len(blobs))
    offset = len(header) + 16 * len(blobs)
    entries, data = b"", b""
    for s, blob in blobs:
        dim = 0 if s >= 256 else s
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset)
        data += blob
        offset += len(blob)
    with open(path, "wb") as f:
        f.write(header + entries + data)


if __name__ == "__main__":
    import os
    import sys

    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication(sys.argv)  # QPixmap を使うのに必要
    here = os.path.dirname(os.path.abspath(__file__))
    if len(sys.argv) > 1:
        CRUMPLE = float(sys.argv[1])
        globals()["CRUMPLE"] = CRUMPLE
    write_ico(os.path.join(here, "icon.ico"))
    draw(256).save(os.path.join(here, "icon_preview.png"))
    print(f"しわくちゃ度 {CRUMPLE} で書き出しました")
