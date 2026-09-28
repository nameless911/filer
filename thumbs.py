"""サムネイルの生成。重くならないことだけを目的に組んである。

Explorer が固まる原因を、順に避ける:
  1. UI を止めない      … 生成は全部ワーカースレッド。画面は常に動く。
  2. 先読みしない        … 見えている行のぶんだけ作る（data() が呼ばれた時に頼む）。
  3. 丸ごと読まない      … QImageReader に縮小指定を渡し、復号の段階で小さくする。
  4. クラウドに触らない  … プレースホルダは対象外。触ると同期が始まってしまう。

さらに、フォルダを移動したら古い依頼の結果は捨てる（世代番号で判定する）。
"""

import os
import zipfile

from PySide6.QtCore import (
    QObject,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    Signal,
)
from PySide6.QtGui import QIcon, QImage, QImageReader, QPixmap

# 大きすぎるものは諦める。開くだけで時間を食うので。
MAX_BYTES = 64 * 1024 * 1024

# 同時に走らせる数。増やしてもディスクが詰まるだけなので控えめにする。
MAX_THREADS = 3


def _supported():
    return {"." + bytes(f).decode().lower() for f in QImageReader.supportedImageFormats()}


# --- 書庫の中に入っているプレビューを取り出す -------------------------------
# 3MF は中身が ZIP で、スライサーがプレビュー画像を同梱している。
# 自分で3Dモデルを描画する必要はなく、入っている絵を出せばよい。

EMBEDDED_PREVIEW = {".3mf"}

# 優先順に見る。Bambu Studio はプレート画像、PrusaSlicer 等は thumbnail.png を入れる。
PREVIEW_NAMES = (
    "Metadata/plate_1.png",
    "Metadata/plate_no_light_1.png",
    "Metadata/top_1.png",
    "Metadata/thumbnail.png",
    "Metadata/plate_1_small.png",
    "thumbnail.png",
)


def _read_embedded(path):
    """書庫からプレビュー画像のバイト列を取り出す。無ければ None。"""
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            lookup = {n.lower(): n for n in names}
            for candidate in PREVIEW_NAMES:
                actual = lookup.get(candidate.lower())
                if actual:
                    return zf.read(actual)
            # 決め打ちで見つからなければ、Metadata 以下の PNG を拾う
            pngs = sorted(
                n for n in names
                if n.lower().startswith("metadata/") and n.lower().endswith(".png")
            )
            if pngs:
                return zf.read(pngs[0])
    except (zipfile.BadZipFile, KeyError, OSError):
        return None
    return None


class _Signals(QObject):
    done = Signal(str, int, QImage)


class _Job(QRunnable):
    def __init__(self, path, box, generation, signals):
        super().__init__()
        self.path = path
        self.box = box
        self.generation = generation
        self.signals = signals

    def run(self):
        ext = os.path.splitext(self.path)[1].lower()
        if ext in EMBEDDED_PREVIEW:
            self._run_embedded()
            return

        reader = QImageReader(self.path)
        reader.setAutoTransform(True)  # 写真の向き（Exif）に従う
        source = reader.size()
        if source.isValid() and not source.isEmpty():
            # 復号しながら縮める。ここが速さの肝で、全画素は展開しない。
            scaled = source.scaled(
                QSize(self.box, self.box), Qt.AspectRatioMode.KeepAspectRatio
            )
            reader.setScaledSize(scaled)
        image = reader.read()
        if image.isNull():
            return
        # QPixmap は GUI スレッド専用。ここでは QImage のまま返す。
        self.signals.done.emit(self.path, self.generation, image)

    def _run_embedded(self):
        data = _read_embedded(self.path)
        if not data:
            return
        image = QImage.fromData(data)
        if image.isNull():
            return
        # 同梱の絵は元々小さいので、読んでから縮める
        if image.width() > self.box or image.height() > self.box:
            image = image.scaled(
                QSize(self.box, self.box),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        self.signals.done.emit(self.path, self.generation, image)


class ThumbnailCache(QObject):
    """欲しい時に頼み、出来たら知らせる。出来るまでは種類アイコンのまま。"""

    ready = Signal(str)  # path

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cache = {}       # key -> QIcon
        self._pending = set()  # key
        self._generation = 0
        self._formats = _supported()
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(MAX_THREADS)
        self._signals = _Signals()
        self._signals.done.connect(self._store)

    def invalidate(self):
        """フォルダを移動したとき等に呼ぶ。走っている依頼の結果を捨てる。"""
        self._generation += 1
        self._pending.clear()

    def can_thumbnail(self, entry):
        if entry.is_dir or entry.placeholder:
            return False  # プレースホルダに触ると同期が走る
        if entry.size < 0 or entry.size > MAX_BYTES:
            return False
        return entry.ext in self._formats or entry.ext in EMBEDDED_PREVIEW

    def get(self, entry, box):
        """出来ていれば QIcon、無ければ None を返し、裏で作り始める。"""
        if not self.can_thumbnail(entry):
            return None
        key = self._key(entry, box)
        icon = self._cache.get(key)
        if icon is not None:
            return icon
        if key not in self._pending:
            self._pending.add(key)
            self._pool.start(_Job(entry.path, box, self._generation, self._signals))
        return None

    def _key(self, entry, box):
        # 中身が変われば作り直す。更新日時と大きさを鍵に混ぜておく。
        return (os.path.normcase(entry.path), int(entry.mtime), entry.size, box)

    def _store(self, path, generation, image):
        if generation != self._generation:
            return  # もう別の場所を見ている
        icon = QIcon(QPixmap.fromImage(image))
        for key in list(self._pending):
            if key[0] == os.path.normcase(path):
                self._cache[key] = icon
                self._pending.discard(key)
        self.ready.emit(path)
