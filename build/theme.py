"""Visual language for the workbook.

One rule drives the colour scheme: a cell's colour tells you whether you may
type in it.  Blue means you type, green means you pick from a list, grey means
the model computed it, amber means advanced, red means something is wrong.
Every one of those is also carried by text somewhere, so the workbook is still
usable in greyscale or with colour-blindness (NFR-8).
"""

INK = 0x1F2933          # body text
MUTED = 0x6B7A8F
RULE = 0xD6DEE8

INPUT_BG = 0xEAF2FD     # blue   - type here
INPUT_FG = 0x123A66
LIST_BG = 0xE8F6EC      # green  - choose from a list
LIST_FG = 0x14532D
CALC_BG = 0xF3F5F8      # grey   - calculated, locked
ADV_BG = 0xFDF4E3       # amber  - advanced
BAD_BG = 0xFDE7E9       # red    - error
BAD_FG = 0x8C1D24
GOOD_BG = 0xE6F4EA
GOOD_FG = 0x1B5E20
WARN_BG = 0xFFF4D6
WARN_FG = 0x7A5200

HDR_BG = 0x1F3A5F       # section headers
HDR_FG = 0xFFFFFF
SUB_BG = 0xDCE6F2
BAND = 0xF7F9FC

# Colour-blind-safe series palette (Okabe-Ito), used for every chart.
SERIES = [0x0072B2, 0xD55E00, 0x009E73, 0xCC79A7, 0xE69F00, 0x56B4E9, 0xF0E442, 0x999999]

FONT = "Liberation Sans"

STYLES = {
    # name:            (props)
    "rp_title":   dict(CharHeight=18, CharWeight=150, CharColor=INK, CharFontName=FONT),
    "rp_h1":      dict(CharHeight=13, CharWeight=150, CharColor=HDR_FG, CellBackColor=HDR_BG,
                       CharFontName=FONT, VertJustify=2),
    "rp_h2":      dict(CharHeight=11, CharWeight=150, CharColor=INK, CellBackColor=SUB_BG,
                       CharFontName=FONT),
    "rp_label":   dict(CharHeight=10, CharColor=INK, CharFontName=FONT),
    "rp_note":    dict(CharHeight=9, CharColor=MUTED, CharPosture=2, CharFontName=FONT),
    "rp_input":   dict(CharHeight=10, CharColor=INPUT_FG, CellBackColor=INPUT_BG,
                       CharWeight=150, CharFontName=FONT, CellProtection=None),
    "rp_list":    dict(CharHeight=10, CharColor=LIST_FG, CellBackColor=LIST_BG,
                       CharWeight=150, CharFontName=FONT),
    "rp_adv":     dict(CharHeight=10, CharColor=INPUT_FG, CellBackColor=ADV_BG,
                       CharWeight=150, CharFontName=FONT),
    "rp_calc":    dict(CharHeight=10, CharColor=MUTED, CellBackColor=CALC_BG, CharFontName=FONT),
    "rp_out":     dict(CharHeight=10, CharColor=INK, CharFontName=FONT),
    "rp_kpi":     dict(CharHeight=20, CharWeight=150, CharColor=HDR_BG, CharFontName=FONT),
    "rp_kpi_lab": dict(CharHeight=9, CharColor=MUTED, CharFontName=FONT),
    "rp_good":    dict(CharHeight=10, CharColor=GOOD_FG, CellBackColor=GOOD_BG,
                       CharWeight=150, CharFontName=FONT),
    "rp_warn":    dict(CharHeight=10, CharColor=WARN_FG, CellBackColor=WARN_BG,
                       CharWeight=150, CharFontName=FONT),
    "rp_bad":     dict(CharHeight=10, CharColor=BAD_FG, CellBackColor=BAD_BG,
                       CharWeight=150, CharFontName=FONT),
    "rp_hdrcol":  dict(CharHeight=9, CharWeight=150, CharColor=HDR_FG, CellBackColor=HDR_BG,
                       CharFontName=FONT, IsTextWrapped=True, VertJustify=2),
}

FORMATS = {
    "money":  '#,##0;[RED]-#,##0',
    "money2": '#,##0.00;[RED]-#,##0.00',
    "pct":    '0.0%',
    "pct2":   '0.00%',
    "num":    '#,##0.00',
    "int":    '#,##0',
    "age":    '0.0',
    "year":   '0',
    "text":   '@',
}
