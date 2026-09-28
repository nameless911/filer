"""見た目の定数を全部ここに置く。色や寸法の不満はこのファイルだけで直る。

方針:
  構造  … Windows 2000 の素直な五層（ツールバー/パンくず/サイドバー/一覧/ステータス）
  作法  … Mac OS X 10.6 の 1px 精度、詰めた行、非アクティブ時に選択色を落とす所作
  配色  … Windows 11 に合わせる。周囲から浮かないことが目的なので既定はこれ。
"""

# --- 寸法（全テーマ共通） ---------------------------------------------------
ROW_HEIGHT = 20        # Explorer より少し詰める
FONT_SIZE = 9          # pt

# ボタンの記号（‹ › ↑ ＋ □ ✕）の大きさ。文字で描いているので pt で指定する。
GLYPH_SIZE = 14        # ツールバー
GLYPH_SIZE_NAV = 19    # 戻る/進む。ここだけ大きくする
# 戻る/進むの記号を下へ押す量(px)。増やすと下がる。
# QToolButton は内部に下方向の余白を持っていて、padding:0 でも 4px 下に寄る。
# 実際に描画した画像を測って打ち消している（フォント計測だけでは分からない）。
NAV_GLYPH_NUDGE = -8
GLYPH_SIZE_TITLE = 11  # タイトルバーの最小化・最大化・閉じる

# 使いたいフォントを上から順に書く。入っている最初のものが使われる。
# 全部無ければシステムの既定にする（その場合 Explorer と同じ顔になる）。
# Osaka は macOS 同梱のフォントなので、Windows には自分で入れる必要がある。
FONT_CANDIDATES = (
    "Osaka",
    "Osaka－等幅",
    "Osaka-Mono",
)
SIDEBAR_WIDTH = 160

# アイコン表示の大きさ。Ctrl+ホイールでこの段を行き来する。
# 途中の値を足したり、最大を増やしたければここだけ直す。
ICON_SIZES = (24, 32, 48, 64, 96, 128, 192)
ICON_SIZE_DEFAULT = 32

# 升目の余白。アイコンの一辺にこれを足したものが升目になる。
# 小さいほど詰まる。高さは文字一行ぶん。名前が折り返すときは、その行数ぶん自動で足される。
# この大きさ未満ではサムネイルを作らない。小さすぎて中身が判別できないので、
# 生成コストだけ払うことになる。
THUMB_MIN_SIZE = 48

ICON_PAD_X = 28
ICON_PAD_Y = 18
ICON_SPACING = 2
# アイコン表示の名前は省略せず折り返す。升目の高さは今のフォルダで一番長い名前に合わせる。
# ただしこの行数を超える分だけは、最終行の真ん中を省略する（極端に長い名前で升目が縦に伸びすぎないように）。
ICON_TEXT_MAX_LINES = 4
# 升目の幅から文字に使えない分を引く量(px)。升目の間隔 2px×2 + 項目の padding 4px×2 + Qt の文字余白 3px×2。
# 小さすぎると Qt 側で文字がはみ出して省略される。
ICON_TEXT_MARGIN = 18
# 升目の最小幅(px)。小さいアイコンでも、よくある長さの名前（Documents 等）が一行か二行に収まる幅。
# 狭くすると詰まるが、名前が細切れに折り返される。
ICON_CELL_MIN_WIDTH = 80

# サイドバーの詰め具合。ここだけで密度が決まる。
# 大きくするほど間延びするので、迷ったら小さいほうを選ぶ。
SIDEBAR_ICON = 16      # アイコンの一辺(px)
SIDEBAR_ROW_PAD = 1    # 行の上下余白(px)。3 にすると前の間隔に戻る。
SIDEBAR_HEAD_PAD = 7   # 見出し（場所/ドライブ）の上の余白(px)
# タブの境目。アクティブなタブの上辺に引く色の帯の太さ(px)。0 にすると帯を消す。
TAB_ACCENT = 2
COL_SIZE_WIDTH = 84
COL_TYPE_WIDTH = 116
COL_DATE_WIDTH = 126
COL_ATTR_WIDTH = 62


# --- パレット ---------------------------------------------------------------
# gradient=True のテーマだけ縦グラデーションを引く。Win11 系はフラットにする。

PALETTES = {
    "win11": {
        "gradient": False,
        "radius": 4,
        "toolbar_top": "#F3F3F3", "toolbar_bottom": "#F3F3F3", "toolbar_border": "#E5E5E5",
        "crumb_top": "#F9F9F9", "crumb_bottom": "#F9F9F9",
        "crumb_text": "#1A1A1A", "crumb_sep": "#9A9A9A",
        "side_bg": "#F3F3F3", "side_border": "#E5E5E5",
        "side_head": "#6A6A6A", "side_text": "#1A1A1A",
        "row_bg": "#FFFFFF", "row_alt": "#FAFAFA",
        "row_text": "#1A1A1A", "row_dim": "#6A6A6A",
        "sel_top": "#CCE4F7", "sel_bottom": "#CCE4F7", "sel_text": "#1A1A1A",
        "sel_inactive_top": "#E8E8E8", "sel_inactive_bottom": "#E8E8E8",
        "sel_inactive_text": "#1A1A1A",
        "head_top": "#FFFFFF", "head_bottom": "#FFFFFF",
        "head_border": "#E5E5E5", "head_sep": "#EAEAEA", "head_text": "#4A4A4A",
        "status_top": "#F3F3F3", "status_bottom": "#F3F3F3", "status_text": "#4A4A4A",
        "btn_top": "#FDFDFD", "btn_bottom": "#FDFDFD", "btn_border": "#D6D6D6",
        "btn_hover": "#EAEAEA", "field_bg": "#FFFFFF",
        "tab_sep": "#C8C8C8", "tab_border": "#D0D0D0", "tab_accent": "#0067C0",
    },
    "win11_dark": {
        "gradient": False,
        "radius": 4,
        "toolbar_top": "#2B2B2B", "toolbar_bottom": "#2B2B2B", "toolbar_border": "#1C1C1C",
        "crumb_top": "#272727", "crumb_bottom": "#272727",
        "crumb_text": "#E4E4E4", "crumb_sep": "#7A7A7A",
        "side_bg": "#202020", "side_border": "#1C1C1C",
        "side_head": "#9A9A9A", "side_text": "#E4E4E4",
        "row_bg": "#191919", "row_alt": "#1E1E1E",
        "row_text": "#E8E8E8", "row_dim": "#9A9A9A",
        "sel_top": "#0F4C81", "sel_bottom": "#0F4C81", "sel_text": "#FFFFFF",
        "sel_inactive_top": "#333333", "sel_inactive_bottom": "#333333",
        "sel_inactive_text": "#D8D8D8",
        "head_top": "#191919", "head_bottom": "#191919",
        "head_border": "#2E2E2E", "head_sep": "#2A2A2A", "head_text": "#B4B4B4",
        "status_top": "#2B2B2B", "status_bottom": "#2B2B2B", "status_text": "#B4B4B4",
        "btn_top": "#323232", "btn_bottom": "#323232", "btn_border": "#3C3C3C",
        "btn_hover": "#3A3A3A", "field_bg": "#1E1E1E",
        "tab_sep": "#4A4A4A", "tab_border": "#454545", "tab_accent": "#4CC2FF",
    },
    # 自宅用。Windows 11 の上で動かすと爆笑を誘うので既定にはしない。
    "snow": {
        "gradient": True,
        "radius": 0,
        "toolbar_top": "#F7F7F7", "toolbar_bottom": "#D9D9D9", "toolbar_border": "#9A9A9A",
        "crumb_top": "#EFEFEF", "crumb_bottom": "#E3E3E3",
        "crumb_text": "#3A3A3A", "crumb_sep": "#AAAAAA",
        "side_bg": "#DCE3EC", "side_border": "#A9B2BD",
        "side_head": "#63707E", "side_text": "#2C2C2C",
        "row_bg": "#FFFFFF", "row_alt": "#EDF3FD",
        "row_text": "#111111", "row_dim": "#666666",
        "sel_top": "#5C90DE", "sel_bottom": "#2C64C4", "sel_text": "#FFFFFF",
        "sel_inactive_top": "#C8C8C8", "sel_inactive_bottom": "#B4B4B4",
        "sel_inactive_text": "#1A1A1A",
        "head_top": "#F8F8F8", "head_bottom": "#E2E2E2",
        "head_border": "#B4B4B4", "head_sep": "#C9C9C9", "head_text": "#3A3A3A",
        "status_top": "#F0F0F0", "status_bottom": "#DADADA", "status_text": "#4A4A4A",
        "btn_top": "#FDFDFD", "btn_bottom": "#E6E6E6", "btn_border": "#A8A8A8",
        "btn_hover": "#D2D2D2", "field_bg": "#FFFFFF",
        "tab_sep": "#A8A8A8", "tab_border": "#9A9A9A", "tab_accent": "#2C64C4",
    },
}

DEFAULT_THEME = "win11"


def detect_theme() -> str:
    """Windows のライト/ダーク設定に追従する。読めなければライト扱い。"""
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        light, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        key.Close()
        return "win11" if light else "win11_dark"
    except (OSError, ImportError):
        return DEFAULT_THEME


def pick_font() -> str:
    """候補のうち、実際に入っている最初のものを返す。無ければ空文字。

    Qt は無いフォント名を指定すると勝手に別のものへ置き換えるので、
    「指定したのに効かない」の原因が分からなくなる。先に実在を確かめる。
    """
    from PySide6.QtGui import QFontDatabase

    installed = {f.lower() for f in QFontDatabase.families()}
    for candidate in FONT_CANDIDATES:
        if candidate.lower() in installed:
            return candidate
    return ""


def build_qss(name: str = DEFAULT_THEME) -> str:
    p = PALETTES[name]
    r = p["radius"]

    def fill(top_key, bottom_key):
        top, bottom = p[top_key], p[bottom_key]
        if not p["gradient"] or top == bottom:
            return top
        return f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {top}, stop:1 {bottom})"

    font = pick_font()
    family = f"font-family: '{font}';" if font else ""

    return f"""
QWidget {{ font-size: {FONT_SIZE}pt; {family} }}
QMainWindow, QWidget#Root {{ background: {p['row_bg']}; }}

#Toolbar {{
    background: {fill('toolbar_top', 'toolbar_bottom')};
    border-bottom: 1px solid {p['toolbar_border']};
}}
#Toolbar QToolButton {{
    background: {fill('btn_top', 'btn_bottom')};
    border: 1px solid {p['btn_border']};
    border-radius: {r}px;
    color: {p['row_text']};
    /* 記号は文字で描いているので、余白を入れると中央からずれる。0 にすること。 */
    font-size: {GLYPH_SIZE}pt;
    padding: 0;
}}
/* 連結したひと組。継ぎ目の線は 1 本だけにする。 */
#Toolbar QToolButton#SegL, #Toolbar QToolButton#NavL {{
    border-top-right-radius: 0; border-bottom-right-radius: 0;
}}
#Toolbar QToolButton#SegR, #Toolbar QToolButton#NavR {{
    border-top-left-radius: 0; border-bottom-left-radius: 0;
    border-left: none;
}}
/* 戻る/進むだけ大きく。移動が主役なので、ここを一番読みやすくする。 */
#Toolbar QToolButton#NavL, #Toolbar QToolButton#NavR {{
    font-size: {GLYPH_SIZE_NAV}pt;
    /* 山括弧は字面が上寄りなので、Qt の行box基準の中央だと上にずれて見える。
       NAV_GLYPH_NUDGE で下へ押して、目で見た中央に合わせる。 */
    padding-top: {NAV_GLYPH_NUDGE}px;
    padding-bottom: 0;
}}
#Toolbar QToolButton:hover {{ background: {p['btn_hover']}; }}
#Toolbar QToolButton:checked {{
    background: {p['sel_top']};
    color: {p['sel_text']};
}}
#Toolbar QToolButton:disabled {{ color: {p['row_dim']}; }}
#Toolbar QLineEdit {{
    border: 1px solid {p['btn_border']};
    border-radius: {max(r, 3)}px;
    padding: 2px 8px;
    background: {p['field_bg']};
    color: {p['row_text']};
}}

#Crumb {{
    background: {fill('crumb_top', 'crumb_bottom')};
    border-bottom: 1px solid {p['head_border']};
    color: {p['crumb_text']};
    padding: 3px 8px;
}}

QListView#IconList {{
    background: {p['row_bg']};
    color: {p['row_text']};
    border: none;
    outline: none;
}}
QListView#IconList::item {{ border-radius: {r}px; padding: 4px; }}
QListView#IconList::item:selected {{
    background: {fill('sel_top', 'sel_bottom')};
    color: {p['sel_text']};
}}
QListView#IconList::item:selected:!active {{
    background: {fill('sel_inactive_top', 'sel_inactive_bottom')};
    color: {p['sel_inactive_text']};
}}

QLineEdit#Address {{
    background: {p['field_bg']};
    border: 1px solid {p['btn_border']};
    border-radius: {max(r, 3)}px;
    color: {p['crumb_text']};
    padding: 3px 8px;
    selection-background-color: {p['sel_top']};
    selection-color: {p['sel_text']};
}}
QLineEdit#Address:focus {{ border: 1px solid {p['sel_bottom']}; }}

#TitleBar {{
    background: {fill('toolbar_top', 'toolbar_bottom')};
    border-bottom: 1px solid {p['toolbar_border']};
}}
#TitleBar QToolButton {{
    background: transparent;
    border: none;
    color: {p['row_text']};
    font-size: {GLYPH_SIZE_TITLE}pt;
    padding: 0;
}}
#TitleBar QToolButton#NewTab {{
    border-radius: {r}px;
    font-size: {GLYPH_SIZE}pt;
    color: {p['row_dim']};
    padding: 0;
}}
#TitleBar QToolButton:hover {{ background: {p['btn_hover']}; }}
/* 閉じるだけ赤。ここは Windows の作法に合わせる。 */
#TitleBar QToolButton#WinClose:hover {{ background: #C42B1C; color: #FFFFFF; }}

QTabBar#Tabs {{
    background: transparent;
    border: none;
}}
/* タブの境目を見せる。
   非アクティブ同士は右端の 1px の仕切り線で区切る（Chrome と同じ）。
   アクティブは枠で囲み、上辺に色の帯を引いて、どれが今のタブか一目で分かるようにする。
   アクティブの左隣の仕切りは枠と二重になるので消す（:next-selected）。 */
QTabBar#Tabs::tab {{
    background: transparent;
    color: {p['row_dim']};
    border: 1px solid transparent;
    border-right: 1px solid {p['tab_sep']};
    border-top: {TAB_ACCENT}px solid transparent;
    padding: 4px 10px;
    margin: 3px 0 0 0;
    border-radius: 0;
    max-width: 200px;
}}
QTabBar#Tabs::tab:next-selected {{ border-right-color: transparent; }}
QTabBar#Tabs::tab:hover:!selected {{
    background: {p['btn_hover']};
    color: {p['row_text']};
}}
QTabBar#Tabs::tab:selected {{
    background: {p['row_bg']};
    color: {p['row_text']};
    border: 1px solid {p['tab_border']};
    border-top: {TAB_ACCENT}px solid {p['tab_accent']};
    border-bottom-color: {p['row_bg']};
    border-top-left-radius: {r}px;
    border-top-right-radius: {r}px;
}}
QTabBar#Tabs::close-button {{ subcontrol-position: right; }}

QMenuBar {{
    background: {fill('toolbar_top', 'toolbar_bottom')};
    color: {p['row_text']};
    border-bottom: 1px solid {p['toolbar_border']};
}}
QMenuBar::item {{ padding: 4px 10px; background: transparent; }}
QMenuBar::item:selected {{ background: {p['btn_hover']}; }}
QMenu {{
    background: {p['field_bg']};
    color: {p['row_text']};
    border: 1px solid {p['btn_border']};
    padding: 4px;
}}
QMenu::item {{ padding: 4px 24px 4px 20px; border-radius: {r}px; }}
QMenu::item:selected {{ background: {p['btn_hover']}; }}
QMenu::separator {{ height: 1px; background: {p['head_sep']}; margin: 4px 6px; }}

#Sidebar {{
    background: {p['side_bg']};
    border: none;
    border-right: 1px solid {p['side_border']};
    color: {p['side_text']};
    outline: none;
}}
#Sidebar::item {{
    padding: {SIDEBAR_ROW_PAD}px 6px;
    border: none;
    border-radius: {r}px;
}}
#Sidebar::item:!enabled {{
    /* 見出し行。上に少しだけ空けて、塊の区切りを作る。 */
    color: {p['side_head']};
    padding-top: {SIDEBAR_HEAD_PAD}px;
}}
#Sidebar::item:selected {{
    background: {fill('sel_top', 'sel_bottom')};
    color: {p['sel_text']};
}}
#Sidebar::item:selected:!active {{
    background: {fill('sel_inactive_top', 'sel_inactive_bottom')};
    color: {p['sel_inactive_text']};
}}

QTreeView#FileList {{
    background: {p['row_bg']};
    alternate-background-color: {p['row_alt']};
    color: {p['row_text']};
    border: none;
    outline: none;
}}
QTreeView#FileList::item {{ padding: 1px 4px; border: none; }}
QTreeView#FileList::item:selected {{
    background: {fill('sel_top', 'sel_bottom')};
    color: {p['sel_text']};
}}
QTreeView#FileList::item:selected:!active {{
    background: {fill('sel_inactive_top', 'sel_inactive_bottom')};
    color: {p['sel_inactive_text']};
}}

QHeaderView {{ background: {p['head_top']}; }}
QHeaderView::section {{
    background: {fill('head_top', 'head_bottom')};
    color: {p['head_text']};
    border: none;
    border-right: 1px solid {p['head_sep']};
    border-bottom: 1px solid {p['head_border']};
    padding: 3px 6px;
}}
QHeaderView::section:last {{ border-right: none; }}

#Status {{
    background: {fill('status_top', 'status_bottom')};
    border-top: 1px solid {p['head_border']};
    color: {p['status_text']};
    padding: 3px 8px;
}}

QScrollBar:vertical {{ background: {p['row_bg']}; width: 12px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: {p['btn_border']}; border-radius: 5px; min-height: 24px; margin: 2px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
"""
