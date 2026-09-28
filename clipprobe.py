"""クリップボードに今何が入っているかを覗く。開発用。

使い方: Explorer でファイルをコピー（または切り取り）してから実行する。
"""

import sys

from PySide6.QtWidgets import QApplication

# Preferred DropEffect の値
EFFECTS = {1: "MOVE（切り取り）", 2: "COPY（コピー）", 4: "LINK（ショートカット）"}


def main():
    app = QApplication(sys.argv)  # noqa: F841 - クリップボードに必要
    mime = QApplication.clipboard().mimeData()

    print("=== 入っている形式 ===")
    for fmt in mime.formats():
        size = len(bytes(mime.data(fmt)))
        print(f"  {fmt}  ({size} バイト)")

    print("\n=== ファイル一覧 (CF_HDROP 由来) ===")
    if mime.hasUrls():
        for url in mime.urls():
            print("  ", url.toLocalFile() or url.toString())
    else:
        print("   ありません")

    print("\n=== Preferred DropEffect ===")
    raw = bytes(mime.data("Preferred DropEffect"))
    if raw:
        value = int.from_bytes(raw[:4], "little")
        print(f"   生データ: {raw.hex(' ')}")
        print(f"   意味    : {value} = {EFFECTS.get(value, '不明')}")
    else:
        print("   ありません（＝コピー扱いになります）")

    if mime.hasText():
        text = mime.text()
        print("\n=== テキスト ===")
        print("  ", text if len(text) < 200 else text[:200] + " …")


if __name__ == "__main__":
    main()
