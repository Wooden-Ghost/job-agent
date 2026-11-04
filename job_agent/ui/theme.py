"""配色与样式表。

想整体换肤只改这一个文件就够了：颜色常量 -> 模板 -> QSS。
用 string.Template（$ 占位）而不是 f-string，是为了让 QSS 里的 { } 不用转义。
"""

from string import Template

# ---------------------------------------------------------------- 颜色
BG = "#F5F6F8"          # 窗口底色
SIDE = "#FFFFFF"        # 侧栏
CARD = "#FFFFFF"        # 卡片
LINE = "#E6E8EB"        # 分割线 / 卡片描边
LINE_SOFT = "#F0F2F5"   # 更淡的分割线
TEXT = "#1F2328"        # 主文字          15.8:1
DIM = "#57606A"         # 次要文字         6.4:1
MUTED = "#6A737D"       # 更次要           4.8:1（原 #9AA4AF 只有 2.5:1，达不到 4.5:1）
ACCENT = "#2563EB"      # 主色             5.2:1
ACCENT_DARK = "#1D4ED8"
ACCENT_SOFT = "#EAF0FE"
OK = "#1A7F37"
OK_SOFT = "#E8F5EC"
WARN = "#8A5A12"
WARN_SOFT = "#FDF6E3"
ERR = "#CF222E"
ERR_SOFT = "#FFEDEC"
FIELD = "#F8F9FB"       # 输入框底色
# 数据库窗口（施工单 §0）：更冷的底色、更淡的分隔线
DB_BG = "#F8F9FA"
DB_LINE = "#EDEFF2"
DB_SUB = "#646A73"       # 次要文字
DB_WEAK = "#8F959E"      # 弱化文字
DB_HOVER = "#F5F6F7"
DB_SELECT = "#E8F1FE"
FONT_CAPTION = 12

FONT = "Microsoft YaHei UI"
MONO = "Consolas"

_QSS = Template("""
/* ---------- 全局 ---------- */
QWidget {
    font-family: "$FONT";
    font-size: 14px;
    color: $TEXT;
}
QWidget#Root { background: $BG; }
QLabel { background: transparent; }
QToolTip {
    background: $TEXT; color: #FFFFFF; border: none;
    padding: 6px 8px; border-radius: 6px; font-size: 12px;
}

/* ---------- 侧栏 ---------- */
QFrame#Sidebar {
    background: $SIDE;
    border-right: 1px solid $LINE;
}
QLabel#Brand   { font-size: 16px; font-weight: 600; color: $TEXT; }
QLabel#BrandSub{ font-size: 12px; color: $MUTED; }

QPushButton#Nav {
    text-align: left;
    padding: 9px 12px 9px 10px;
    border: none;
    border-left: 2px solid transparent;
    border-radius: 8px;
    color: $DIM;
    font-size: 14px;
    background: transparent;
}
QPushButton#Nav:hover   { background: $LINE_SOFT; color: $TEXT; }
QPushButton#Nav:checked {
    background: $ACCENT_SOFT; color: $ACCENT; font-weight: 600;
    border-left: 2px solid $ACCENT;
}

/* ---------- 卡片 ---------- */
QFrame#Card {
    background: $CARD;
    border: 1px solid $LINE;
    border-radius: 12px;
}
QFrame#CardTight {
    background: $CARD;
    border: 1px solid $LINE;
    border-radius: 10px;
}
QFrame#PathField {
    background: $FIELD; border: 1px solid $LINE; border-radius: 8px;
}
QLabel#Link { font-size: 14px; color: $ACCENT; background: transparent; }
QLabel#PathText { font-size: 14px; color: $TEXT; background: transparent; }
QFrame#Banner {
    background: $WARN_SOFT; border: 1px solid #F2E3C0; border-radius: 8px;
}
QLabel#BannerText { font-size: 13px; color: $WARN; background: transparent; }
QFrame#HLine { background: $LINE; border: none; }
QFrame#VLine { background: $LINE; border: none; }

QLabel#PageTitle { font-size: 20px; font-weight: 600; }
QLabel#PageDesc  { font-size: 14px; color: $DIM; }
QLabel#CardTitle { font-size: 14px; font-weight: 600; }
QLabel#CardSub   { font-size: 12px; color: $MUTED; }
QLabel#SectionHint { font-size: 12px; color: $MUTED; }
QLabel#FieldLabel  { font-size: 14px; color: $TEXT; }
QLabel#FieldSub    { font-size: 12px; color: $MUTED; }
QLabel#FieldValue  { font-size: 14px; color: $TEXT; }
QLabel#Big         { font-size: 28px; font-weight: 600; }
QLabel#BigNum      { font-size: 28px; font-weight: 600; }
QLabel#StatusLine { font-size: 14px; color: $ACCENT; padding: 2px 0 0 0; }
QLabel#LogStep     { font-size: 14px; font-weight: 600; }
QLabel#TileValue   { font-size: 20px; font-weight: 600; }
QLabel#HelpDot {
    border: 1px solid $LINE; border-radius: 8px;
    color: $MUTED; font-size: 11px;
}
QLabel#TileLabel   { font-size: 12px; color: $MUTED; }
QLabel#DetailTitle  { font-size: 18px; font-weight: 600; color: $TEXT; }
QLabel#DetailSalary { font-size: 16px; font-weight: 600; color: $ACCENT; }
QTextEdit#JdBox {
    background: transparent; border: none;
    font-size: 14px; color: $TEXT;
    line-height: 1.7;
}
QTableWidget#JobList { background: transparent; }
QWidget#DbRoot { background: $DB_BG; }
QTableWidget#DbList {
    background: transparent;
    border: none;
    outline: none;
}
QTableWidget#DbList::item:selected { background: transparent; }
QLineEdit#InlineEdit {
    background: #FFFFFF;
    border: 1px solid $ACCENT;
    border-radius: 6px;
    padding: 0 6px;
    font-size: 13px;
}
QLabel#DbHint {
    color: $DB_WEAK;
    font-size: 12px;
    padding: 6px 2px;
}
QLabel#DbSection {
    color: $DB_SUB;
    font-size: 12px;
    font-weight: 600;
    padding-top: 2px;
}
QTextEdit#DbNote {
    background: $FIELD;
    border: 1px solid $DB_LINE;
    border-radius: 8px;
    padding: 6px 8px;
    font-size: 13px;
}

/* ---------- 按钮 ---------- */
QPushButton#Primary {
    background: $ACCENT; color: #FFFFFF; border: none;
    border-radius: 8px; padding: 8px 18px; min-height: 18px; font-weight: 600;
}
QPushButton#Primary:hover    { background: $ACCENT_DARK; }
QPushButton#Primary:disabled { background: #C7D2E4; color: #FFFFFF; }

QPushButton#Secondary {
    background: $CARD; color: $TEXT;
    border: 1px solid $LINE; border-radius: 8px; padding: 7px 16px; min-height: 18px;
}
QPushButton#Secondary:hover { background: $LINE_SOFT; }
QPushButton#Secondary:disabled, QPushButton#Danger:disabled {
    background: $LINE_SOFT; color: $MUTED; border-color: $LINE_SOFT;
}

QPushButton#Ghost {
    background: transparent; color: $ACCENT;
    border: none; padding: 6px 8px;
}
QPushButton#Ghost:hover { color: $ACCENT_DARK; text-decoration: underline; }

QPushButton#Danger {
    background: $CARD; color: $ERR;
    border: 1px solid $LINE; border-radius: 8px; padding: 7px 16px; min-height: 18px;
}
QPushButton#Danger:hover { background: $ERR_SOFT; }

QPushButton#Secondary:focus, QPushButton#Danger:focus {
    border: 2px solid $ACCENT; padding: 7px 15px;
}
QPushButton#Nav:focus { border: 1px solid $ACCENT; }
QPushButton#Ghost:focus { text-decoration: underline; }

QPushButton#Chip {
    background: $LINE_SOFT; color: $DIM;
    border: none; border-radius: 13px; padding: 5px 12px; font-size: 12px;
}
QPushButton#Chip:hover   { background: #E6E9EE; color: $TEXT; }
QPushButton#Chip:checked { background: $ACCENT_SOFT; color: $ACCENT; font-weight: 600; }
QPushButton#ChipAdd {
    background: transparent; color: $MUTED;
    border: 1px dashed #CFD6DE; border-radius: 13px; padding: 5px 12px; font-size: 12px;
}
QPushButton#ChipAdd:hover { color: $ACCENT; border-color: $ACCENT; }

QFrame#Seg { background: $LINE_SOFT; border: none; border-radius: 9px; }
QPushButton#SegItem {
    background: transparent; color: $DIM; border: none;
    border-radius: 7px; padding: 6px 14px; font-size: 12px;
}
QPushButton#SegItem:hover   { color: $TEXT; }
QPushButton#SegItem:checked { background: $CARD; color: $TEXT; font-weight: 600; }

/* ---------- 工具栏 ---------- */
QFrame#Toolbar {
    background: $CARD; border: 1px solid $LINE; border-radius: 10px;
}
QFrame#Toolbar QLabel#ToolName { font-size: 13px; color: $MUTED; }
QFrame#VLine { background: $LINE; border: none; }
QPushButton#IconBtn {
    background: transparent; border: none; border-radius: 8px;
}
QPushButton#IconBtn:hover { background: $LINE_SOFT; }
QComboBox QAbstractItemView::item:disabled { color: $MUTED; }
QComboBox#ToolCombo {
    background: $CARD; border: 1px solid $LINE; border-radius: 8px;
    padding: 6px 26px 6px 10px; min-width: 96px;
}
QComboBox#ToolCombo:hover { border-color: #CFD6DE; }

/* ---------- 输入 ---------- */
QLineEdit, QSpinBox, QComboBox {
    background: $FIELD;
    border: 1px solid $LINE;
    border-radius: 8px;
    padding: 6px 10px;
    selection-background-color: $ACCENT_SOFT;
    selection-color: $TEXT;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: $ACCENT; background: $CARD; }
QSpinBox::up-button, QSpinBox::down-button {
    width: 0px; height: 0px; border: none; background: transparent;
}
QSpinBox::up-arrow, QSpinBox::down-arrow { width: 0px; height: 0px; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: $CARD; border: 1px solid $LINE; border-radius: 8px;
    selection-background-color: $ACCENT_SOFT; selection-color: $TEXT;
    outline: none; padding: 4px;
}

/* ---------- 滑块 ---------- */
QSlider { min-height: 24px; }
QSlider::groove:horizontal {
    height: 6px; background: $LINE_SOFT; border-radius: 3px;
}
QSlider::sub-page:horizontal {
    height: 6px; background: $ACCENT; border-radius: 3px;
}
QSlider::handle:horizontal {
    width: 16px; height: 16px; margin: -5px 0;
    background: #FFFFFF; border: 2px solid $ACCENT; border-radius: 8px;
}

/* ---------- 进度 ---------- */
QProgressBar {
    background: $LINE_SOFT; border: none; border-radius: 4px;
    height: 8px; text-align: center; color: transparent;
}
QProgressBar::chunk { background: $ACCENT; border-radius: 4px; }

/* ---------- 表格 ---------- */
QTableWidget {
    background: $CARD; border: none; gridline-color: transparent;
    selection-background-color: $ACCENT_SOFT;
    selection-color: $TEXT;
}
QHeaderView::section {
    background: $CARD; color: $MUTED; border: none;
    border-bottom: 1px solid $LINE; padding: 10px 6px; font-size: 12px;
}
QTableWidget::item { padding: 8px 4px; border-bottom: 1px solid $LINE_SOFT; }
QTableWidget::item:hover { background: $LINE_SOFT; }
QTableWidget::item:selected { background: $ACCENT_SOFT; color: $TEXT; }

/* ---------- 日志 ---------- */
QTextEdit#LogBox {
    background: #FBFCFD;
    border: 1px solid $LINE;
    border-radius: 8px;
    font-family: "$MONO";
    font-size: 12px;
    padding: 8px;
}

/* ---------- 滚动条 ---------- */
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical {
    background: #D5DAE1; border-radius: 4px; min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #C2C9D2; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; border: none; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QScrollBar:horizontal { height: 10px; background: transparent; margin: 2px; }
QScrollBar::handle:horizontal {
    background: #D5DAE1; border-radius: 4px; min-width: 30px;
}
""")

QSS = _QSS.substitute(
    FONT=FONT, MONO=MONO, BG=BG, SIDE=SIDE, CARD=CARD, LINE=LINE,
    LINE_SOFT=LINE_SOFT, TEXT=TEXT, DIM=DIM, MUTED=MUTED, ACCENT=ACCENT,
    ACCENT_DARK=ACCENT_DARK, ACCENT_SOFT=ACCENT_SOFT, ERR=ERR, ERR_SOFT=ERR_SOFT,
    FIELD=FIELD, OK=OK, OK_SOFT=OK_SOFT, WARN=WARN, WARN_SOFT=WARN_SOFT,
    DB_BG=DB_BG, DB_LINE=DB_LINE, DB_SUB=DB_SUB, DB_WEAK=DB_WEAK,
)
