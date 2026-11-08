from nicegui import ui

BG = "#0f1426"
SIDEBAR_BG = "#0f1426"
GLASS_BG = "#16162a"
GLASS_BORDER = "#2d2d48"
TILE_BG = "#1e1e38"
TILE_BORDER = "#33335a"
ACCENT = "#4A9BE8"
ACCENT_HOVER = "#6CB4EE"
SUCCESS = "#66ff99"
WARN = "#ffaa44"
ERROR = "#ff6666"
PINK = "#ff66aa"
MUTED = "#9aa4b2"
TEXT = "#e8ecf1"

GRADE_COLORS = {
    "XH": "#ffd700", "X": "#ffd700",
    "SH": "#ff69b4", "S": "#ff69b4",
    "A": "#00ff7f", "B": "#1e90ff",
    "C": "#ff4500", "D": "#ff0000",
}
GRADE_ORDER = ["XH", "X", "SH", "S", "A", "B", "C", "D"]


def apply_theme():
    ui.add_head_html(
        f"""
<style>
/* JetBrains Mono everywhere (except icon glyphs) */
* {{
    font-family: 'JetBrains Mono', 'Cascadia Mono', Consolas, monospace !important;
}}
.material-icons,
.material-symbols-outlined,
.material-symbols-rounded,
.material-symbols-sharp,
.q-icon {{
    font-family: 'Material Icons' !important;
}}

/* hard dark surfaces — kill any white default */
html, body {{
    background: {BG} !important;
}}
.q-page {{
    background: {BG} !important;
}}
.q-tab-panels, .q-tab-panel {{
    background: transparent !important;
}}
.q-card {{
    background: {TILE_BG} !important;
    color: {TEXT} !important;
    box-shadow: none !important;
    border-radius: 10px !important;
    border: 1px solid {TILE_BORDER} !important;
}}

.header-bar {{
    background: {GLASS_BG};
    border-bottom: 1px solid {GLASS_BORDER};
    padding: 10px 18px;
}}

/* left sidebar with the tabs (same background as the whole window) */
.sidebar {{
    background: transparent;
    border-right: 1px solid {GLASS_BORDER};
}}
.sidebar-tabs .q-tab {{
    justify-content: center;
    align-items: center;
    text-align: center;
    padding: 9px 14px;
    margin: 2px 10px;
    border-radius: 8px;
    color: #c9d1e0;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    font-size: 13px;
    font-weight: 600;
}}
.sidebar-tabs .q-tab__content {{
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 4px;
    text-align: center;
}}
.sidebar-tabs .q-tab:hover {{
    background: rgba(255,255,255,0.09);
    color: #ffffff;
}}
.sidebar-tabs .q-tab--active {{
    background: rgba(74,155,232,0.20);
    border: 1px solid {ACCENT};
    color: #ffffff;
}}
.sidebar-tabs .q-tab__label {{
    font-size: 13px;
    font-weight: 600;
    text-align: center;
}}

/* Nested Ranked submenu */
.ranked-submenu-btn {{
    box-sizing: border-box;
    min-width: 0;
}}
.ranked-submenu-btn .q-btn__content {{
    justify-content: flex-start;
    text-align: left;
    width: 100%;
}}
.ranked-submenu-btn .q-btn__content > * {{
    min-width: 0;
}}

/* header status chips */
.status-chip {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 10px;
    border-radius: 999px;
    background: rgba(255,255,255,0.07);
    border: 1px solid rgba(255,255,255,0.14);
    color: #ffffff;
    font-weight: 600;
    font-size: 12px;
}}
.status-chip .dot {{
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
}}

/* tiles & panels */
.tile {{
    background: {TILE_BG} !important;
    border: 1px solid {TILE_BORDER};
    border-radius: 10px;
    padding: 10px 14px;
}}
.tile .label {{
    font-size: 10px;
    color: #8b95a7;
    text-transform: uppercase;
    letter-spacing: 0.8px;
}}
.tile .value {{
    font-size: 19px;
    font-weight: 700;
    color: #ffffff;
}}

.panel {{
    background: {GLASS_BG} !important;
    border: 1px solid {GLASS_BORDER};
    border-radius: 12px;
    padding: 14px 16px;
}}
.panel .panel-title {{
    font-size: 13px;
    font-weight: 700;
    color: #e0e0e0;
    margin-bottom: 8px;
}}
.panel-accent {{
    background: {GLASS_BG} !important;
    border: 2px solid {ACCENT};
    border-radius: 12px;
    padding: 14px 16px;
}}

.log-widget {{
    background: #0a0a14 !important;
    border: 1px solid {GLASS_BORDER};
    border-radius: 10px;
    padding: 10px;
    font-size: 12px;
    color: #88cc88;
}}

/* inputs & switches in dark */
.q-field--outlined .q-field__control {{
    background: rgba(255,255,255,0.04) !important;
    color: #ffffff;
}}
.q-field__native {{
    color: #ffffff !important;
}}
.q-field__label {{
    color: #8b95a7 !important;
}}
.q-checkbox__label, .q-toggle__label {{
    color: #cfd6e4 !important;
}}

.mono {{
    font-family: 'JetBrains Mono', Consolas, monospace;
}}

.ap-badge {{
    width: 42px;
    height: 42px;
    flex-shrink: 0;
    line-height: 0;
}}
.ap-badge svg {{
    width: 42px;
    height: 42px;
    display: block;
}}
</style>
"""
    )