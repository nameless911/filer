# Filer

PySide6 製の Windows 用ファイラー。

- 構造は Windows 2000（ツールバー / アドレス / サイドバー / 一覧 / ステータスの五層）
- 作法は Mac OS X 10.6、配色は Windows 11
- キー操作は Chrome に合わせる
- コピー・移動・削除は OS（`SHFileOperation`）に任せ、削除は必ずゴミ箱経由

設計の決めごとは [DESIGN.md](DESIGN.md)、他のファイラーとの対照は [DESIGN-others.md](DESIGN-others.md) にまとめてある。

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![PySide6](https://img.shields.io/badge/PySide6-6.x-green)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)

---

## exe で使う（Python 不要）

[Releases](../../releases) から次のどちらかを落とす。

| ファイル | 説明 |
|---|---|
| `Filer-portable.exe` | exe 1 個。置いてダブルクリックするだけ。起動は少し遅い |
| `Filer.zip` | フォルダ版。展開して `Filer.exe` を起動。起動が速い |

---

## ソースから動かす

```bash
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
run.bat
```

- `run.bat` はコンソールなしで起動する。引数にフォルダを渡すとそこを開く
- `debug.bat` はコンソールを残すので、エラーを見たいときに使う
- どちらも `.venv` があればその Python を使い、無ければ PATH の Python を使う

画面を出さずに組み立てだけ確かめるには：

```bash
.venv\Scripts\python.exe smoke.py
```

---

## exe をビルドする

```bash
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\pyinstaller.exe --noconfirm Filer.spec
.venv\Scripts\pyinstaller.exe --noconfirm Filer-portable.spec
```

`dist\Filer\`（フォルダ版）と `dist\Filer-portable.exe`（1 個版）ができる。

まとめてやるスクリプトもある：

```bash
powershell -ExecutionPolicy Bypass -File build.ps1                    # ビルドと zip 化
powershell -ExecutionPolicy Bypass -File build.ps1 -Release v0.2.0    # + タグ付け・push・Releases 公開
```

### コミットしたら自動でビルドし直す

クローンしたあと一度だけ：

```bash
git config core.hooksPath .githooks
```

以後はコミットするたびに裏で `build.ps1` が走り、`dist\` が最新になる（結果は `build.log`）。
ビルドを飛ばしたいときは `SKIP_BUILD=1 git commit ...`（Git Bash の場合）。
Releases への公開は自動ではしない。出したいときに `-Release` を付けて実行する。

アイコンを作り直すときは `python appicon.py`（`icon.ico` と `icon_preview.png` を書き出す）。

---

## ファイル構成

| ファイル | 持っているもの |
|---|---|
| `main.py` | ウィンドウの組み立てと画面遷移、操作の判断（起動点） |
| `view.py` | 描画とタブ、ドラッグの受け口 |
| `model.py` | 列挙・並び順・表示文字列（Qt に依存しない） |
| `theme.py` | 色・寸法・テーマ |
| `actions.py` | 名前の検証とクリップボード |
| `osops.py` | OS に投げる呼び出しだけ（移植時の差し替え点） |
| `thumbs.py` | サムネイル生成 |
| `winframe.py` | Windows 固有の枠の描画 |
| `appicon.py` | アイコン（しわくちゃ度つき） |
| `smoke.py` | 画面を出さない組み立て検証（開発用） |
| `clipprobe.py` | クリップボード調査用（開発用） |
