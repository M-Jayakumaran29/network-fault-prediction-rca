"""
Builds the project presentation (16 slides, 16:9) with python-pptx.
Palette: dark brown, coffee brown, caramel, tan, beach sand, cream, white.
Every number on the slides comes from the project's own files
(models/threshold.json, models/ml_rca_report.json, README) or from runs
made while building the project; nothing is invented.

Run:  python presentation/build_deck.py
"""
import os
from PIL import ImageFont
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.oxml.ns import qn
from lxml import etree

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "Network_Fault_Prediction_RCA.pptx")
FIG = os.path.join(ROOT, "models", "figures")
DASH = os.path.join(HERE, "assets", "dashboard.png")

# ---- palette (brown, beach sand, white) ------------------------------------
ESP = "3B2416"      # espresso (dark backgrounds, main text)
BROWN = "6F4E37"    # coffee
CARAMEL = "A9744F"  # accent
TAN = "C8A27C"
SAND = "EADBC8"     # beach sand
CREAM = "FBF6EE"    # light beach background
WHITE = "FFFFFF"
MUTED = "8A7260"
TITLE_FONT, BODY_FONT, MONO = "Cambria", "Calibri", "Courier New"

W, H = 13.333, 7.5
LM = 0.6
CW = W - 2 * LM  # content width

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(W), Inches(H)
BLANK = prs.slide_layouts[6]
TOTAL = 17
_fit_warnings = []

_fonts = {}
def _font(bold, size, serif=False):
    key = (bold, serif)
    if key not in _fonts:
        name = ("cambriab.ttf" if bold else "cambria.ttc") if serif else ("calibrib.ttf" if bold else "calibri.ttf")
        _fonts[key] = os.path.join("C:/Windows/Fonts", name)
    return ImageFont.truetype(_fonts[key], int(size * 10))

def rgb(h): return RGBColor.from_string(h)

# ---- text helpers -----------------------------------------------------------
def P(text="", sz=16, b=False, c=ESP, bullet=False, sa=6, al="l", font=BODY_FONT, runs=None, it=False):
    return dict(text=text, sz=sz, b=b, c=c, bullet=bullet, sa=sa, al=al, font=font, runs=runs, it=it)

def _para_lines(p, width_pt):
    """Estimated wrapped line count for one paragraph (greedy word wrap)."""
    runs = p["runs"] or [(p["text"], p["b"])]
    words = []
    for t, bold in runs:
        for i, w_ in enumerate(t.split(" ")):
            words.append((w_, bold))
    avail = width_pt - (0.22 * 72 if p["bullet"] else 0)
    lines, cur = 1, 0.0
    for w_, bold in words:
        f = _font(bold, p["sz"], p["font"] == TITLE_FONT)
        ww = f.getlength(w_ + " ") / 10.0
        if cur + ww > avail and cur > 0:
            lines += 1; cur = ww
        else:
            cur += ww
    return lines

def est_height_in(paras, w_in):
    tot = 0.0
    for p in paras:
        if p["font"] == MONO:
            lines = 1
        else:
            lines = _para_lines(p, w_in * 72)
        tot += lines * p["sz"] * 1.2 + p["sa"]
    return tot / 72.0

def add_text(slide, x, y, w, h, paras, anchor="t", label="", margin=0.0, fit=True):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(margin)
    tf.margin_top = tf.margin_bottom = Inches(margin)
    tf.vertical_anchor = {"t": MSO_ANCHOR.TOP, "m": MSO_ANCHOR.MIDDLE, "b": MSO_ANCHOR.BOTTOM}[anchor]
    fill_paras(tf, paras)
    if fit:
        need = est_height_in(paras, w - 2 * margin)
        if need > h - 2 * margin + 0.02:
            _fit_warnings.append(f"{label or paras[0]['text'][:30]!r}: needs {need:.2f}in, box {h - 2*margin:.2f}in")
    return tb

def fill_paras(tf, paras):
    first = True
    for p in paras:
        para = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        para.alignment = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER, "r": PP_ALIGN.RIGHT}[p["al"]]
        para.space_after = Pt(p["sa"])
        para.space_before = Pt(0)
        runs = p["runs"] or [(p["text"], p["b"])]
        for t, bold in runs:
            r = para.add_run()
            r.text = t
            r.font.size = Pt(p["sz"]); r.font.bold = bold; r.font.italic = p["it"]
            r.font.name = p["font"]; r.font.color.rgb = rgb(p["c"])
        pPr = para._p.get_or_add_pPr()
        if p["bullet"]:
            pPr.set("marL", str(int(0.22 * 914400))); pPr.set("indent", str(int(-0.22 * 914400)))
            for tag in ("a:buNone", "a:buChar"):
                for e in pPr.findall(qn(tag)): pPr.remove(e)
            bu = etree.SubElement(pPr, qn("a:buChar")); bu.set("char", "•")
        else:
            pPr.set("marL", "0"); pPr.set("indent", "0")
            etree.SubElement(pPr, qn("a:buNone"))

def no_shadow(shape):
    shape.shadow.inherit = False

def add_box(slide, x, y, w, h, fill=WHITE, line=None, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06, lw=0.75):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    s.fill.solid(); s.fill.fore_color.rgb = rgb(fill)
    if line:
        s.line.color.rgb = rgb(line); s.line.width = Pt(lw)
    else:
        s.line.fill.background()
    no_shadow(s)
    s.text_frame.text = ""
    return s

def box_text(shape, paras, anchor="m", margin=0.12):
    tf = shape.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(margin)
    tf.margin_top = tf.margin_bottom = Inches(margin * 0.6)
    tf.vertical_anchor = {"t": MSO_ANCHOR.TOP, "m": MSO_ANCHOR.MIDDLE, "b": MSO_ANCHOR.BOTTOM}[anchor]
    fill_paras(tf, paras)

def labeled_box(slide, x, y, w, h, paras, fill=WHITE, line=None, anchor="m", margin=0.12, radius=0.06, label=""):
    s = add_box(slide, x, y, w, h, fill, line, radius=radius)
    box_text(s, paras, anchor, margin)
    need = est_height_in(paras, w - 2 * margin)
    if need > h - 1.2 * margin + 0.02:
        _fit_warnings.append(f"box {label or paras[0]['text'][:30]!r}: needs {need:.2f}in, box {h - 1.2*margin:.2f}in")
    return s

def circle(slide, cx, cy, d, fill, text="", sz=14, tc=WHITE, bold=True):
    s = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(cx - d / 2), Inches(cy - d / 2), Inches(d), Inches(d))
    s.fill.solid(); s.fill.fore_color.rgb = rgb(fill); s.line.fill.background(); no_shadow(s)
    if text:
        box_text(s, [P(text, sz=sz, b=bold, c=tc, al="c", sa=0)], margin=0.0)
    return s

def arrow_right(slide, x, y, w=0.3, h=0.3, fill=CARAMEL):
    s = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid(); s.fill.fore_color.rgb = rgb(fill); s.line.fill.background(); no_shadow(s)
    return s

def line(slide, x1, y1, x2, y2, color=TAN, w=2.0):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = rgb(color); c.line.width = Pt(w)
    etree.SubElement(c._element.spPr, qn('a:effectLst'))
    return c

def notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text

def new_slide(n, tag, title, note, dark=False):
    s = prs.slides.add_slide(BLANK)
    s.background.fill.solid(); s.background.fill.fore_color.rgb = rgb(ESP if dark else CREAM)
    if tag:
        add_text(s, LM, 0.36, 8, 0.28, [P(tag.upper(), sz=12, b=True, c=TAN if dark else CARAMEL, sa=0)], label="tag")
    if title:
        add_text(s, LM, 0.62, CW, 0.75, [P(title, sz=30, b=True, c=CREAM if dark else ESP, sa=0, font=TITLE_FONT)],
                 anchor="m", label=f"title{n}")
    add_text(s, LM, 7.1, 8, 0.25, [P("AI-Based Network Fault Prediction and Root Cause Analysis", sz=10, c=TAN if dark else MUTED, sa=0)], fit=False)
    add_text(s, W - LM - 1.5, 7.1, 1.5, 0.25, [P(f"{n} / {TOTAL}", sz=10, c=TAN if dark else MUTED, al="r", sa=0)], fit=False)
    notes(s, note)
    return s

def make_table(slide, x, y, col_w, rows, row_h, header_fill=BROWN, sz=13, header_sz=13, first_col_bold=False,
               aligns=None, zebra=True):
    nrows, ncols = len(rows), len(col_w)
    gf = slide.shapes.add_table(nrows, ncols, Inches(x), Inches(y), Inches(sum(col_w)), Inches(row_h * nrows))
    tbl = gf.table
    for j, cw in enumerate(col_w): tbl.columns[j].width = Inches(cw)
    for i in range(nrows): tbl.rows[i].height = Inches(row_h)
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = tbl.cell(i, j)
            cell.margin_left = cell.margin_right = Inches(0.1)
            cell.margin_top = cell.margin_bottom = Inches(0.04)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            hdr = i == 0
            cell.fill.solid()
            cell.fill.fore_color.rgb = rgb(header_fill if hdr else (WHITE if (i % 2 == 1 or not zebra) else SAND))
            tf = cell.text_frame; tf.word_wrap = True
            para = tf.paragraphs[0]
            al = (aligns[j] if aligns else "l")
            para.alignment = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER, "r": PP_ALIGN.RIGHT}[al]
            r = para.add_run(); r.text = str(val)
            r.font.size = Pt(header_sz if hdr else sz)
            r.font.bold = hdr or (first_col_bold and j == 0)
            r.font.name = BODY_FONT
            r.font.color.rgb = rgb(WHITE if hdr else ESP)
            # width check
            f = _font(r.font.bold, sz)
            if f.getlength(str(val)) / 10.0 > (col_w[j] - 0.2) * 72 * 1.02 and not hdr:
                lines = _para_lines(P(str(val), sz=sz, b=bool(r.font.bold)), (col_w[j] - 0.2) * 72)
                if lines * sz * 1.2 / 72 + 0.08 > row_h:
                    _fit_warnings.append(f"table cell {val!r} wraps to {lines} lines (row {row_h}in)")
    return gf

# =============================================================== SLIDE 1: title
s = new_slide(1, "", "", "Hello everyone. Our project predicts network faults before they happen and finds their cause. "
              "We use the LCORE-D dataset, which is a recording of a simulated internet-provider network. "
              "The project has two objectives and a web dashboard. I will explain each objective with a small example.", dark=True)
add_text(s, LM, 1.7, 7.1, 2.6, [P("AI-Based Network Fault Prediction and Root Cause Analysis",
                                    sz=38, b=True, c=CREAM, sa=0, font=TITLE_FONT)], anchor="t", label="deck title")
add_text(s, LM, 4.45, 7.1, 0.5, [P("Predict the fault. Find the cause.", sz=22, c=TAN, sa=0, it=True)], label="tagline")
add_text(s, LM, 5.5, 7.1, 1.1, [P("Dataset: LCORE-D (Mendeley Data, version 2)", sz=16, c=SAND, sa=4),
                                 P("Presented by: [Student names]   |   Guide: [Guide name]", sz=16, c=SAND, sa=0)], label="title meta")
# motif: the inferred device chain (R6 omitted for space)
pos = {"SERVER": (8.75, 3.8), "EDGE-MS": (9.75, 3.8), "R1": (10.75, 3.8), "R2": (11.75, 3.8), "R3": (12.55, 3.8),
       "R4": (12.55, 2.5), "R5": (12.55, 5.1)}
chain = [("SERVER", "EDGE-MS"), ("EDGE-MS", "R1"), ("R1", "R2"), ("R2", "R3"), ("R3", "R4"), ("R3", "R5")]
for a, b in chain:
    line(s, pos[a][0], pos[a][1], pos[b][0], pos[b][1], color=BROWN, w=3)
labels = {"SERVER": "SRV", "EDGE-MS": "EDG", "R1": "R1", "R2": "R2", "R3": "R3", "R4": "R4", "R5": "R5"}
for k, (cx, cy) in pos.items():
    circle(s, cx, cy, 0.62, TAN if k != "R3" else CARAMEL, labels[k], sz=12, tc=ESP if k != "R3" else WHITE)
add_text(s, 8.2, 5.75, 4.9, 0.3, [P("Simulated ISP core network (R6 not drawn)", sz=12, c=TAN, al="c", sa=0)], fit=False)

# =============================================================== SLIDE 2: problem
s = new_slide(2, "Overview", "Why this project?",
              "Networks carry our data. When a router or link fails, users lose their connection. "
              "Usually the fault is noticed after it starts, and then engineers must find the cause by hand. "
              "Our idea is to warn early and find the cause automatically.")
cards = [("1", "Faults stop services", "When a router or a link fails, users lose their connection until it is fixed."),
         ("2", "Faults are found late", "Most monitoring tells us after a problem has started, not before it."),
         ("3", "Diagnosis is slow", "Engineers must trace the problem by hand through many devices and counters.")]
cw = 3.85; gap = (CW - 3 * cw) / 2
for i, (num, head, body) in enumerate(cards):
    x = LM + i * (cw + gap)
    add_box(s, x, 1.8, cw, 3.3, fill=WHITE, line=SAND, lw=1)
    circle(s, x + 0.65, 2.6, 0.75, BROWN, num, sz=22)
    add_text(s, x + 0.35, 3.3, cw - 0.7, 0.5, [P(head, sz=21, b=True, c=ESP, sa=0, font=TITLE_FONT)], label=f"card head {i}")
    add_text(s, x + 0.35, 3.9, cw - 0.7, 1.1, [P(body, sz=16, c=ESP, sa=0)], label=f"card body {i}")
b = add_box(s, LM, 5.45, CW, 1.2, fill=BROWN)
box_text(b, [P("Our idea: warn early and find the cause automatically.", sz=22, b=True, c=WHITE, al="c", sa=0, font=TITLE_FONT)], margin=0.3)

# =============================================================== SLIDE 3: objectives
s = new_slide(3, "Overview", "The two objectives",
              "The project has two objectives. Objective one predicts a fault with an LSTM. Objective two finds the cause with rules and the network map. "
              "A dashboard shows both.")
two_cards = [("OBJECTIVE 1", "Predict", "An LSTM reads the last 10 minutes of a device and predicts whether it will be in a fault state one minute later."),
             ("OBJECTIVE 2", "Find the cause", "Rules and the network map name the device, the port and the likely fault type, and list the evidence.")]
tw = (CW - 0.3) / 2
for i, (tag, head, body) in enumerate(two_cards):
    x = LM + i * (tw + 0.3)
    add_box(s, x, 1.8, tw, 3.4, fill=WHITE, line=SAND, lw=1)
    chip = add_box(s, x + 0.3, 2.05, 1.75, 0.38, fill=BROWN, radius=0.4)
    box_text(chip, [P(tag, sz=13, b=True, c=WHITE, al="c", sa=0)], margin=0.02)
    add_text(s, x + 0.3, 2.65, tw - 0.6, 0.55, [P(head, sz=26, b=True, c=ESP, sa=0, font=TITLE_FONT)], label=f"obj head {i}")
    add_text(s, x + 0.3, 3.4, tw - 0.6, 1.7, [P(body, sz=18, c=ESP, sa=0)], label=f"obj body {i}")
b = add_box(s, LM, 5.5, CW, 1.0, fill=SAND)
box_text(b, [P("A web dashboard shows prediction, cause, history charts and the network map, live.", sz=18, b=True, c=ESP, al="c", sa=0)], margin=0.25)

# =============================================================== SLIDE 4: dataset
s = new_slide(4, "Data", "The dataset: LCORE-D",
              "LCORE-D is a public dataset from Mendeley Data. It was recorded from a simulated internet-provider network built in GNS3. "
              "We have seven monitored devices, one reading per device per minute, and a label for every reading. "
              "H means healthy, T is a short glitch that was not injected, and F is a serious fault that the researchers injected. "
              "There is also a fault log with the type of each injected fault.")
stats = [("7", "devices monitored"), ("407 h", "of monitoring"), ("169,712", "readings, one per device per minute"), ("69", "logged fault events")]
for i, (big, small) in enumerate(stats):
    x = LM + (i % 2) * 2.95; y = 1.8 + (i // 2) * 2.4
    add_box(s, x, y, 2.75, 2.2, fill=WHITE, line=SAND, lw=1)
    add_text(s, x + 0.15, y + 0.3, 2.45, 0.9, [P(big, sz=36, b=True, c=BROWN, al="c", sa=0, font=TITLE_FONT)], anchor="m", label=f"stat {big}")
    add_text(s, x + 0.2, y + 1.25, 2.35, 0.8, [P(small, sz=15, c=ESP, al="c", sa=0)], label=f"stat label {big}")
add_text(s, 6.75, 1.85, 5.98, 4.8, [
    P(runs=[("Simulated, not real. ", True), ("Recorded from an ISP core network built in the GNS3 simulator.", False)], sz=17, bullet=True, sa=16),
    P(runs=[("Every reading has a label. ", True), ("H healthy 73,593; T short glitch 93,466; F injected fault 2,622.", False)], sz=17, bullet=True, sa=16),
    P(runs=[("Fault Log. ", True), ("Start, end and type of each logged fault, such as link failure or misconfiguration.", False)], sz=17, bullet=True, sa=16),
    P(runs=[("Source. ", True), ("Singh and Gupta, Mendeley Data v2, 2025 (CC BY 4.0).", False)], sz=17, bullet=True, sa=0),
], label="dataset bullets")

# =============================================================== SLIDE 5: devices and ports
s = new_slide(5, "Data", "Devices and ports in the data",
              "A device is a router. A router has several ports where cables connect it to other devices. Each port is called an interface, and each keeps its own counters. "
              "The seven devices have different numbers of ports, so the seven files have different numbers of columns. "
              "For prediction we add the ports together. For root cause analysis we look at each port again.")
add_box(s, LM, 1.7, 5.8, 3.4, fill=WHITE, line=SAND, lw=1)
rt = add_box(s, 1.1, 1.95, 2.6, 2.9, fill=BROWN)
box_text(rt, [P("Router", sz=22, b=True, c=WHITE, al="c", sa=2, font=TITLE_FONT), P("example: CORE-R3", sz=14, c=SAND, al="c", sa=2),
              P("4 ports", sz=14, c=SAND, al="c", sa=0)])
for i, lab in enumerate(["b4", "b5", "b6", "b7"]):
    cy = 2.3 + i * 0.78
    line(s, 3.95, cy, 5.1, cy, color=TAN, w=2.5)
    pbx = add_box(s, 3.45, cy - 0.25, 0.5, 0.5, fill=SAND, line=BROWN, shape=MSO_SHAPE.RECTANGLE, lw=1.25)
    box_text(pbx, [P(lab, sz=13, b=True, c=ESP, al="c", sa=0)], margin=0.0)
    circle(s, 5.4, cy, 0.58, TAN, "dev", sz=11, tc=ESP)
add_text(s, 6.75, 1.75, 5.98, 3.5, [
    P("A device (router) has several ports. Each port is an interface.", sz=16, bullet=True, sa=9),
    P("Each interface keeps its own counters: data in and out, errors, discards, up or down, speed.", sz=16, bullet=True, sa=9),
    P("Devices have different numbers of ports, so the files have 32 to 51 columns.", sz=16, bullet=True, sa=9),
    P("Prediction adds a device's ports into one set of numbers. Root cause analysis looks at each port again.", sz=16, bullet=True, sa=0),
], label="ports bullets")
add_text(s, LM, 5.3, 8, 0.32, [P("Our 7 devices and their ports (22 ports in total)", sz=15, b=True, c=BROWN, sa=0)], label="chips label")
devs = [("CORE-R1", 3), ("CORE-R2", 2), ("CORE-R3", 4), ("CORE-R4", 3), ("CORE-R5", 3), ("CORE-R6", 4), ("EDGE-MS", 3)]
chw = 1.6; chg = (CW - 7 * chw) / 6
for i, (d, n) in enumerate(devs):
    x = LM + i * (chw + chg)
    c = add_box(s, x, 5.7, chw, 0.95, fill=SAND if d != "EDGE-MS" else TAN)
    box_text(c, [P(d, sz=15, b=True, c=ESP, al="c", sa=1), P(f"{n} ports", sz=14, c=ESP, al="c", sa=0)], margin=0.05)

# =============================================================== SLIDE 6: architecture
s = new_slide(6, "Design", "System architecture",
              "This is the whole system. Data is cleaned and turned into six numbers per device per minute. "
              "The LSTM gives a fault probability, and a threshold of 0.22 decides yes or no. If yes, objective two checks nine rules and reports the cause. "
              "The dashboard shows every step.")
cg = 0.5
colw = (CW - 2 * cg) / 3
cols = [("DATA", BROWN, ["LCORE-D files: 7 devices", "Clean names, combine ports", "6 numbers per device per minute", "10-minute windows, time order kept"]),
        ("OBJECTIVE 1 · PREDICT", CARAMEL, ["LSTM model", "Fault probability, 0 to 1", "Threshold 0.22", "Fault predicted? If yes, go on"]),
        ("OBJECTIVE 2 · FIND CAUSE", BROWN, ["Collect clues: numbers, ports, map", "Check the nine rules", "Highest weight gives the fault type", "Report device, port, type, evidence"])]
for i, (head, col, items) in enumerate(cols):
    x = LM + i * (colw + cg)
    hb = add_box(s, x, 1.7, colw, 0.55, fill=col)
    box_text(hb, [P(head, sz=14, b=True, c=WHITE, al="c", sa=0)], margin=0.05)
    for j, it_ in enumerate(items):
        y = 2.4 + j * 0.98
        bx = add_box(s, x, y, colw, 0.84, fill=WHITE, line=SAND, lw=1)
        box_text(bx, [P(it_, sz=15, c=ESP, al="c", sa=0)], margin=0.1)
    if i < 2:
        arrow_right(s, x + colw + (cg - 0.3) / 2, 3.6, 0.3, 0.32)
bar = add_box(s, LM, 6.4, CW, 0.52, fill=SAND)
box_text(bar, [P("Web dashboard: status, metrics, probability, cause, charts and network map", sz=14, b=True, c=ESP, al="c", sa=0)], margin=0.05)

# =============================================================== SLIDES 7-9: preprocessing (simple)
# ---- slide 7: raw columns -> 6 numbers
s = new_slide(7, "Objective 1", "From raw files to 6 numbers",
              "Each raw file has 32 to 51 columns. Most of them are the same few measurements repeated for every port of the router. "
              "We keep what we need and add the ports together, so every router has just six numbers per minute: packet loss, latency, throughput, discards, errors, and how many ports are up. "
              "The label, fault or healthy, is the answer the model must predict. It is never given to the model as an input.")
add_box(s, LM, 1.7, 5.0, 4.1, fill=WHITE, line=SAND, lw=1)
add_text(s, LM + 0.3, 1.85, 4.4, 0.4, [P("Raw file (one per router)", sz=18, b=True, c=BROWN, sa=0, font=TITLE_FONT)], label="raw head")
raw_items = [("Ping results", "loss and delay"), ("Port counters", "traffic, errors, drops, status, for every port"),
             ("The label", "fault or healthy"), ("Map facts", "hops and dependents")]
for k, (h_, d_) in enumerate(raw_items):
    c = add_box(s, LM + 0.3, 2.4 + k * 0.76, 4.4, 0.64, fill=SAND)
    box_text(c, [P(h_, sz=15, b=True, c=ESP, sa=0), P(d_, sz=13, c=ESP, sa=0)], margin=0.1)
add_text(s, LM + 0.3, 5.5, 4.4, 0.3, [P("32 to 51 columns in total", sz=13, c=MUTED, al="c", sa=0)], fit=False)
arrow_right(s, 5.8, 3.55, 0.5, 0.5)
add_box(s, 6.45, 1.7, 6.28, 4.1, fill=WHITE, line=SAND, lw=1)
add_text(s, 6.75, 1.85, 5.7, 0.4, [P("6 numbers per router per minute", sz=18, b=True, c=BROWN, sa=0, font=TITLE_FONT)], label="six head")
six = [("Packet loss", "from the ping test"), ("Latency", "from the ping test"),
       ("Throughput", "all ports, bits ÷ 60"), ("Discards", "all ports added"),
       ("Errors", "all ports added"), ("Ports up", "share of ports up")]
for k, (h_, d_) in enumerate(six):
    x = 6.75 + (k % 2) * 2.95
    y = 2.4 + (k // 2) * 1.08
    c = add_box(s, x, y, 2.75, 0.92, fill=BROWN if k < 2 else CARAMEL if k < 4 else TAN)
    tc = WHITE if k < 4 else ESP
    box_text(c, [P(h_, sz=16, b=True, c=tc, al="c", sa=1), P(d_, sz=13, c=tc, al="c", sa=0)], margin=0.06)
b = add_box(s, LM, 6.05, CW, 0.8, fill=SAND)
box_text(b, [P("The answer to predict: fault (label T or F) or healthy (H), one minute later.", sz=17, b=True, c=ESP, al="c", sa=0)], margin=0.2)

# ---- slide 9: time split and pieces
s = new_slide(8, "Objective 1", "Split by time and cut into 10-minute pieces",
              "We split by time, not randomly. About eighty percent of the data, the oldest part, is for learning. The other twenty percent is held out: fifteen percent for checking and tuning, which is called validation, and about five percent, the newest part, for the final test. "
              "That way the model never learns from the future. The test part is small because the recording has long idle gaps. "
              "Each piece is ten minutes of six numbers from one router, and the answer is the label one minute after the piece. A piece never crosses a gap, a router change, or the border between the parts.")
add_text(s, LM, 1.65, CW, 0.35, [P("1. Split the timeline (oldest to newest, never shuffled)", sz=16, b=True, c=BROWN, sa=0)], label="split head")
segs = [("TRAIN: learn (about 80%)", 0.797, BROWN, WHITE, "132,714 pieces"), ("CHECK (15%)", 0.148, CARAMEL, WHITE, "24,608"), ("TEST", 0.055, ESP, WHITE, "8,974")]
x = LM
for name, frac, col, tc, cap in segs:
    w_ = CW * frac
    seg = add_box(s, x, 2.1, w_ - 0.04, 0.75, fill=col, shape=MSO_SHAPE.RECTANGLE)
    box_text(seg, [P(name, sz=15, b=True, c=tc, al="c", sa=0)], margin=0.04)
    add_text(s, x, 2.92, w_ - 0.04, 0.3, [P(cap, sz=13, c=MUTED, al="c", sa=0)], fit=False)
    x += w_
add_text(s, LM, 3.3, CW, 0.35, [P("About 80% trains the model. The other 20% is held out: 15% to check and tune (validation) and about 5% for the final test.", sz=14, c=ESP, sa=0)], label="split note")
add_text(s, LM, 4.0, CW, 0.35, [P("2. One piece = 10 minutes of 6 numbers from one router", sz=16, b=True, c=BROWN, sa=0)], label="piece head")
bw = 0.72; bg = 0.1
for k in range(10):
    bx = add_box(s, LM + k * (bw + bg), 4.5, bw, 0.8, fill=SAND, line=TAN, shape=MSO_SHAPE.RECTANGLE, lw=1)
    box_text(bx, [P(f"min {k + 1}", sz=13, b=True, c=ESP, al="c", sa=0)], margin=0.02)
ax = LM + 10 * (bw + bg)
arrow_right(s, ax + 0.05, 4.65, 0.5, 0.5)
ans = add_box(s, ax + 0.7, 4.5, 12.73 - (ax + 0.7), 0.8, fill=BROWN)
box_text(ans, [P("Answer: fault or healthy at minute 11", sz=13, b=True, c=WHITE, al="c", sa=0)], margin=0.06)
add_text(s, LM, 5.65, CW, 1.2, [
    P("A piece is dropped if it would cross a gap in the recording, a change of router, or the border between train, check and test.", sz=15, bullet=True, sa=6),
    P("Numbers are shrunk using the training part only, so nothing leaks from the future.", sz=15, bullet=True, sa=0)], label="piece notes")

# =============================================================== SLIDE 10: why LSTM + architecture
s = new_slide(9, "Objective 1", "Why an LSTM, and how its unit is built",
              "Our data is a time series: the order of the minutes matters, because a fault usually builds up over several minutes. "
              "An LSTM reads the minutes in order and has gates that keep useful notes and forget the rest, so it can use something from minute two when it reaches minute ten. "
              "On the right is one LSTM unit. The top belt is the memory. The old memory passes the forget gate, which keeps part of it. "
              "Then the input gate and the candidate add new information from this minute, which gives the new memory. The output gate decides how much of it is shown. "
              "All four parts see the same inputs: today's six numbers and yesterday's output. Our model has 64 of these units side by side. "
              "To be honest, we did not test other models, so we cannot claim the LSTM is better. Comparing it with simpler models is future work.")
reasons = [("Order matters", "Faults build up over minutes. The LSTM reads 10 minutes in order."),
           ("It remembers", "Its gates keep useful notes, so minute 2 can still help at minute 10."),
           ("It spots trends", "A one-minute model cannot see rising or jumping loss. The LSTM can."),
           ("It fits the task", "The brief asked for an LSTM on time-series data.")]
for k, (h_, d_) in enumerate(reasons):
    y = 1.65 + k * 1.05
    add_box(s, LM, y, 5.0, 0.93, fill=WHITE, line=SAND, lw=1)
    circle(s, LM + 0.42, y + 0.465, 0.5, BROWN, str(k + 1), sz=16)
    add_text(s, LM + 0.85, y + 0.06, 4.05, 0.82, [P(h_, sz=15.5, b=True, c=ESP, sa=1), P(d_, sz=13.5, c=ESP, sa=0)], anchor="m", label=f"why {k}")

add_box(s, 5.85, 1.65, 6.88, 4.25, fill=WHITE, line=SAND, lw=1)
add_text(s, 6.05, 1.75, 6.5, 0.3, [P("Inside one LSTM unit", sz=14.5, b=True, c=BROWN, sa=0)], fit=False)
by = 2.2; bh = 0.62; cy = by + bh / 2
om = add_box(s, 6.05, by, 1.3, bh, fill=SAND, line=TAN)
box_text(om, [P("Old memory", sz=13, b=True, c=ESP, al="c", sa=0)], margin=0.03)
arrow_right(s, 7.4, cy - 0.14, 0.38, 0.28)
circle(s, 8.15, cy, 0.52, BROWN, "×", sz=18)
arrow_right(s, 8.5, cy - 0.14, 0.75, 0.28, fill=TAN)
circle(s, 9.55, cy, 0.52, BROWN, "+", sz=20)
arrow_right(s, 9.88, cy - 0.14, 0.3, 0.28)
nm = add_box(s, 10.25, by, 1.3, bh, fill=SAND, line=TAN)
box_text(nm, [P("New memory", sz=13, b=True, c=ESP, al="c", sa=0)], margin=0.03)
arrow_right(s, 11.58, cy - 0.14, 0.25, 0.28)
ob = add_box(s, 11.85, by, 0.75, bh, fill=BROWN)
box_text(ob, [P("Output", sz=12, b=True, c=WHITE, al="c", sa=0)], margin=0.02)

gy = 3.45
gates = [(7.1, 1.75, "Forget gate", "keep old memory?", 8.15, by + bh),
         (8.95, 1.2, "Input gate", "let in?", 9.55, by + bh),
         (10.25, 1.15, "Candidate", "new info", 9.55, by + bh),
         (11.5, 1.1, "Output gate", "show?", 12.22, by + bh)]
for x_, w_, h_, d_, tx, ty in gates:
    line(s, x_ + w_ / 2, gy, tx, ty, color=TAN, w=2.25)
for x_, w_, h_, d_, tx, ty in gates:
    g = add_box(s, x_, gy, w_, 0.9, fill=WHITE, line=CARAMEL, lw=1.5)
    box_text(g, [P(h_, sz=12.5, b=True, c=BROWN, al="c", sa=1), P(d_, sz=12, c=ESP, al="c", sa=0)], margin=0.04)
ib = add_box(s, 6.9, 4.9, 5.7, 0.6, fill=ESP)
box_text(ib, [P("Inputs each minute: today's 6 numbers + yesterday's output", sz=12.5, b=True, c=CREAM, al="c", sa=0)], margin=0.08)
for x_, w_, h_, d_, tx, ty in gates:
    line(s, x_ + w_ / 2, gy + 0.9, x_ + w_ / 2, 4.9, color=TAN, w=2.25)
add_text(s, 6.05, 5.53, 6.5, 0.28, [P("Our model has 64 of these units side by side.", sz=12.5, c=MUTED, al="c", sa=0)], fit=False)

bn = add_box(s, LM, 6.05, CW, 0.8, fill=SAND)
box_text(bn, [P("Honest note: we did not test other models, so we cannot say the LSTM is better. A comparison is future work.", sz=15, b=True, c=ESP, al="c", sa=0)], margin=0.2)

# =============================================================== SLIDE 8: LSTM model
s = new_slide(10, "Objective 1", "Objective 1: the LSTM fault predictor",
              "An LSTM is a neural network that reads data in order, so it can notice trends such as packet loss rising. "
              "Our model has an LSTM layer with 64 units, dropout to avoid memorizing, a dense layer, and a sigmoid output between zero and one. "
              "In simple words: it studies about 130,000 examples that come with the correct answer. After each guess it checks how wrong it was and adjusts its inner numbers. It practises in rounds, 64 examples at a time, and is tested on the check data after every round. When that score stops improving, it stops and keeps the best version, which happened after 8 rounds. While practising it hides 30 percent of its numbers at random so it does not just memorise.")
flow = [("Input", "10 min × 6 numbers", SAND, ESP), ("LSTM", "64 units", BROWN, WHITE), ("Dropout", "0.3", TAN, ESP),
        ("Dense", "32 units, ReLU", TAN, ESP), ("Dense", "1 unit, sigmoid", CARAMEL, WHITE), ("Output", "fault probability", ESP, WHITE)]
fw = 1.75; fg = (CW - 6 * fw) / 5
for i, (h_, sub, fc, tc) in enumerate(flow):
    x = LM + i * (fw + fg)
    b = add_box(s, x, 1.75, fw, 1.15, fill=fc)
    box_text(b, [P(h_, sz=16, b=True, c=tc, al="c", sa=1), P(sub, sz=13, c=tc, al="c", sa=0)], margin=0.06)
    if i < 5: arrow_right(s, x + fw + (fg - 0.26) / 2, 2.17, 0.26, 0.3)
add_box(s, LM, 3.2, 7.3, 3.5, fill=WHITE, line=SAND, lw=1)
add_text(s, LM + 0.3, 3.38, 6.7, 3.25, [
    P("How it learns (in simple words)", sz=19, b=True, c=BROWN, sa=8, font=TITLE_FONT),
    P("It studies about 130,000 examples. Each one comes with the correct answer: fault or healthy.", sz=15, bullet=True, sa=6),
    P("After each guess it checks how wrong it was, then adjusts its inner numbers to be less wrong next time.", sz=15, bullet=True, sa=6),
    P("It practises in rounds, looking at 64 examples at a time.", sz=15, bullet=True, sa=6),
    P("After every round it is tested on the check data. When the score stops improving, it stops and keeps the best version.", sz=15, bullet=True, sa=6),
    P("While practising, it hides 30% of its numbers at random so it does not just memorise.", sz=15, bullet=True, sa=0),
], label="how it learns")
add_box(s, 8.1, 3.2, 4.63, 3.5, fill=SAND)
add_text(s, 8.4, 3.38, 4.05, 3.25, [
    P("Settings", sz=19, b=True, c=BROWN, sa=8, font=TITLE_FONT),
    P(runs=[("Mistake measure (loss): ", True), ("binary cross-entropy", False)], sz=14.5, sa=7),
    P(runs=[("Adjuster (optimizer): ", True), ("Adam, step 0.001", False)], sz=14.5, sa=7),
    P(runs=[("Examples at a time: ", True), ("64", False)], sz=14.5, sa=7),
    P(runs=[("Rounds it ran: ", True), ("8, then stopped early", False)], sz=14.5, sa=7),
    P(runs=[("Best check score (loss): ", True), ("0.299", False)], sz=14.5, sa=0),
], label="settings")

# =============================================================== SLIDE 11: LSTM at each minute
s = new_slide(11, "Objective 1", "What the LSTM does at each minute",
              "The LSTM goes through the ten minutes in order. At every minute it looks at that minute's six numbers and the notes it kept from the minute before. "
              "Four small decisions happen: how much old memory to keep, how much new information to let in, what the new information is, and how much memory to show to the next step. "
              "Then the memory and the output are updated and passed on. The table shows real numbers from one memory unit in our example. At minute one the memory is almost empty, and at minute ten it holds a summary of the whole window. "
              "The same happens in all 64 units, and in the end their outputs give the fault probability.")
bw7 = 0.9; gp7 = (11.7 - 10 * bw7) / 9
for k in range(10):
    bx = add_box(s, LM + k * (bw7 + gp7), 1.7, bw7, 0.62, fill=BROWN if k in (0, 9) else SAND, line=TAN, shape=MSO_SHAPE.RECTANGLE, lw=1)
    box_text(bx, [P(f"min {k + 1}", sz=13.5, b=True, c=WHITE if k in (0, 9) else ESP, al="c", sa=0)], margin=0.02)
    if k < 9:
        arrow_right(s, LM + k * (bw7 + gp7) + bw7 + (gp7 - 0.2) / 2, 1.9, 0.2, 0.22)
add_text(s, LM, 2.4, CW, 0.3, [P("Each minute passes its memory and output to the next minute.", sz=14, c=MUTED, al="c", sa=0)], fit=False)

gates = [("Forget gate", "How much of the old memory do I keep?"), ("Input gate", "How much new information do I let in?"),
         ("Candidate", "What is the new information?"), ("Output gate", "How much memory do I show next?")]
gw = 2.85; gg = (CW - 4 * gw) / 3
for k, (h_, d_) in enumerate(gates):
    x = LM + k * (gw + gg)
    c = add_box(s, x, 2.85, gw, 1.3, fill=WHITE, line=SAND, lw=1)
    box_text(c, [P(h_, sz=16.5, b=True, c=BROWN, al="c", sa=3, font=TITLE_FONT), P(d_, sz=14, c=ESP, al="c", sa=0)], margin=0.12)

fb = add_box(s, LM, 4.4, CW, 0.7, fill=ESP)
box_text(fb, [P("new memory = forget × old memory + input × candidate        new output = output gate × tanh(memory)", sz=15, b=True, c=CREAM, al="c", sa=0)], margin=0.15)

rows = [["Unit 0 (real numbers)", "Forget", "Input", "Candidate", "Output gate", "Memory", "Output"],
        ["Minute 1 (memory starts at 0)", "0.739", "0.329", "-0.045", "0.471", "-0.015", "-0.007"],
        ["Minute 10 (last minute)", "0.530", "0.097", "-0.657", "0.340", "-0.186", "-0.063"]]
make_table(s, LM, 5.3, [3.1, 1.5, 1.5, 1.5, 1.6, 1.45, 1.48], rows, 0.43, sz=14, header_sz=14, first_col_bold=True,
           aligns=["l", "c", "c", "c", "c", "c", "c"])
add_text(s, LM, 6.68, CW, 0.3, [P("CORE-R2 test window, memory unit 0 of 64. Minutes 2 to 9 work the same way. Check for minute 1: 0.739 × 0 + 0.329 × (-0.045) = -0.015.", sz=12.5, c=MUTED, sa=0)], fit=False)

# =============================================================== SLIDE 13: how the threshold was chosen
s = new_slide(12, "Objective 1", "How the threshold 0.22 was chosen",
              "The model gives a probability, but we need a yes or no. The threshold is the line between them. "
              "After training, we tried every threshold from 0.05 to 0.95 on the validation data, which the model did not learn from. For each one we scored the result with the F1 score, and we kept the best, which was 0.22. "
              "F1 balances two things: recall, which is how many real faults we caught, and precision, which is how many of our alarms were real. "
              "For example, with precision 0.771 and recall 0.976, F1 is 2 times 0.771 times 0.976, divided by 0.771 plus 0.976, which is 0.861. "
              "To be honest, the choice barely matters. A threshold of 0.30 gives the same F1 and 0.50 is almost equal.")
steps13 = [("Train first", "The LSTM gives every validation example a probability."),
           ("Try many thresholds", "Every value from 0.05 to 0.95, in steps of 0.01."),
           ("Score each one", "Call it a fault at or above the threshold, then measure the F1 score."),
           ("Keep the best", "0.22 scored highest. It is then fixed for the test data and the dashboard.")]
for k, (h_, d_) in enumerate(steps13):
    y = 1.75 + k * 1.02
    circle(s, LM + 0.3, y + 0.42, 0.56, BROWN, str(k + 1), sz=18)
    add_text(s, LM + 0.85, y, 5.3, 0.95, [P(h_, sz=18, b=True, c=ESP, sa=1), P(d_, sz=15, c=ESP, sa=0)], label=f"thr step {k}")
add_box(s, 7.0, 1.7, 5.73, 4.25, fill=WHITE, line=SAND, lw=1)
add_text(s, 7.3, 1.85, 5.15, 2.6, [
    P("What is F1?", sz=19, b=True, c=BROWN, sa=8, font=TITLE_FONT),
    P(runs=[("Recall: ", True), ("of all real faults, how many did we catch?", False)], sz=15.5, bullet=True, sa=6),
    P(runs=[("Precision: ", True), ("of all our alarms, how many were real?", False)], sz=15.5, bullet=True, sa=6),
    P(runs=[("F1 ", True), ("balances both: 2 × precision × recall ÷ (precision + recall)", False)], sz=15.5, bullet=True, sa=0),
], label="f1 text")
ex = add_box(s, 7.3, 4.45, 5.13, 1.3, fill=BROWN)
box_text(ex, [P("Example (test data)", sz=13.5, b=True, c=TAN, sa=3),
              P("precision 0.771, recall 0.976", sz=15, c=WHITE, sa=2),
              P("F1 = 2 × 0.771 × 0.976 ÷ (0.771 + 0.976) = 0.861", sz=15, b=True, c=WHITE, sa=0)], anchor="m", margin=0.15)
bn = add_box(s, LM, 6.15, CW, 0.75, fill=SAND)
box_text(bn, [P("On validation data, 0.22 gave the best F1 (0.934). The choice barely matters: 0.30 scores the same and 0.50 is almost equal.", sz=15.5, b=True, c=ESP, al="c", sa=0)], margin=0.2)

# =============================================================== SLIDE 11: RCA overview
s = new_slide(13, "Objective 2", "Objective 2: Root cause analysis (rules, no ML)",
              "Objective two starts only when objective one predicts a fault. It collects clues: the device's numbers, each port's own counters, the device's normal values, other devices at the same minute, and the network map. "
              "It checks nine rules. Every rule that matches adds evidence with a weight. The highest weight gives the fault type. "
              "The weights are added to give a low, medium or high evidence level. This is a count of evidence, not a probability.")
add_box(s, LM, 1.7, 5.95, 2.85, fill=WHITE, line=SAND, lw=1)
add_text(s, LM + 0.3, 1.88, 5.35, 2.6, [
    P("When and what it looks at", sz=18, b=True, c=BROWN, sa=7, font=TITLE_FONT),
    P("Starts only after the LSTM predicts a fault.", sz=16, bullet=True, sa=6),
    P("The router's numbers and each port's own counters.", sz=16, bullet=True, sa=6),
    P("The router's normal (healthy) values.", sz=16, bullet=True, sa=6),
    P("Other routers at the same minute, and the network map.", sz=16, bullet=True, sa=0),
], label="rca left")
add_box(s, 6.78, 1.7, 5.95, 2.85, fill=WHITE, line=SAND, lw=1)
add_text(s, 7.08, 1.88, 5.35, 2.6, [
    P("How it decides", sz=18, b=True, c=BROWN, sa=7, font=TITLE_FONT),
    P("Check all nine rules.", sz=16, bullet=True, sa=6),
    P("Each match adds evidence with a weight (1 to 4).", sz=16, bullet=True, sa=6),
    P("The highest weight gives the fault type and the port.", sz=16, bullet=True, sa=6),
    P("Weights added: 6 or more high, 3 to 5 medium, below 3 low. An evidence count, not a probability.", sz=16, bullet=True, sa=0),
], label="rca right")
eb = add_box(s, LM, 4.8, CW, 2.05, fill=ESP)
add_text(s, LM + 0.3, 4.95, 6, 0.3, [P("Real result from a test on a CORE-R1 fault row", sz=13, b=True, c=TAN, sa=0)], label="out head", fit=False)
add_text(s, LM + 0.3, 5.35, CW - 0.6, 1.4, [
    P("affected device : CORE-R1          affected port : u", sz=15, c=CREAM, sa=4, font=MONO),
    P("fault type      : link_failure     rule : severe_icmp_loss", sz=15, c=CREAM, sa=4, font=MONO),
    P("evidence        : ICMP loss on CORE-R1 = 100.0% (threshold 80.0%)", sz=15, c=CREAM, sa=4, font=MONO),
    P("evidence level  : medium (rule-based, not an ML probability)", sz=15, c=CREAM, sa=0, font=MONO),
], label="rca output", fit=False)

# =============================================================== SLIDE 12: rules
s = new_slide(14, "Objective 2", "Objective 2: the nine rules",
              "These are the nine rules. For example, rule one says that if the monitoring agent is silent, the device is probably down. "
              "Rule three says that if one port has most of the errors, its hardware is probably faulty. Rule eight says that if several devices fail together, blame the device above them. "
              "The limits are based on each device's healthy values and were chosen by us. They are not learned from data.")
rows = [["#", "Rule", "Condition", "Suggests", "Weight"],
        ["1", "Device unreachable", "Monitoring agent (SNMP) is silent", "Node failure", "4"],
        ["2", "Interface down", "Some ports are not up", "Link failure", "3"],
        ["3", "Localized errors", "One port: errors > 5 and > 5× normal; others clean", "Line-card failure", "3"],
        ["4", "Discards spike", "Discards > 5 and > 5× normal", "Link or overload", "2"],
        ["5", "Severe packet loss", "Loss is 80% or more", "Link failure", "3"],
        ["6", "ICMP blocked", "Loss 30% or more, agent works, no errors", "Firewall blocks pings", "2"],
        ["7", "Routing latency", "Latency > 3× normal, loss under 30%", "Routing problem", "2"],
        ["8", "Shared upstream", "Several devices fail together", "Blame device above", "4"],
        ["9", "Fallback", "Nothing else matched", "Short glitch", "1"]]
make_table(s, LM, 1.6, [0.55, 2.55, 5.0, 2.9, 1.13], rows, 0.47, sz=14, header_sz=14, aligns=["c", "l", "l", "l", "c"])
add_text(s, LM, 6.45, CW, 0.5, [P("Limits come from each device's own healthy values and were chosen by us. They are not learned.", sz=14.5, c=BROWN, b=True, sa=0)], label="rules note")

# =============================================================== SLIDE 13: why rules
s = new_slide(15, "Objective 2", "Rules or ML? Neither names the fault type well",
              "We tested both ways to name the fault type from the Fault Log. On later, unseen events the random forest was right 31 percent of the time and our rules 41 percent. "
              "But simply guessing the most common type would be right 43 percent of the time on those rows. Cross-validated over all events, ML got 22 percent against 19 percent for guessing. "
              "So neither beats guessing, and the rules reach 41 percent mostly by saying multiple link failure almost every time. Nearly every fault minute hits five to seven devices at once, and only 69 faults are logged, so the numbers cannot tell the fault types apart. "
              "We keep the rules because they show where the problem is and give a readable reason. The ML code is still there and can be switched on in config.py.")
rows = [["Method", "Accuracy"],
        ["ML (random forest), held-out later events", "31%"],
        ["Rules, same rows", "41%"],
        ["Guess the most common type, same rows", "43%"],
        ["ML, cross-validated over all events (9 types)", "22%"],
        ["Guess the most common type, all events", "19%"]]
make_table(s, LM, 1.7, [4.7, 1.7], rows, 0.55, sz=14.5, header_sz=14.5, aligns=["l", "c"])
add_text(s, LM, 5.2, 6.4, 1.6, [
    P("Macro-F1 is low: ML 0.20, rules 0.11. The rules reach 41% mostly by saying multiple link failure almost every time.", sz=14.5, sa=7),
    P("Labels come from the Fault Log, which names no device, so they are approximate.", sz=14.5, sa=0)], label="rf note")
add_box(s, 7.4, 1.7, 5.33, 5.1, fill=WHITE, line=SAND, lw=1)
add_text(s, 7.7, 1.9, 4.75, 4.8, [
    P("What this tells us", sz=19, b=True, c=BROWN, sa=8, font=TITLE_FONT),
    P("Neither rules nor ML beat guessing the most common type on later events.", sz=15, bullet=True, sa=7),
    P("Nearly all fault minutes hit 5 to 7 devices at once, and only 69 faults are logged.", sz=15, bullet=True, sa=7),
    P("So the numbers cannot separate fault types. RCA is most useful for where the problem is, with evidence.", sz=15, bullet=True, sa=7),
    P("We keep rules: every answer has a readable reason. The ML code is kept but switched off.", sz=15, bullet=True, sa=0),
], label="why rules")

# =============================================================== SLIDE 16: dashboard
s = new_slide(16, "Demo", "The dashboard",
              "This is the dashboard. It replays held-out test data one minute at a time through both objectives. "
              "The banner shows the status. The panels show the metrics, the LSTM probability against the threshold, and the root cause analysis result. "
              "The map shows the network with the affected device highlighted, and below are four history charts. In this screenshot, CORE-R2 shows a predicted fault with its root cause analysis.")
s.shapes.add_picture(DASH, Inches(LM), Inches(1.65), height=Inches(5.25))
add_text(s, 6.95, 1.7, 5.78, 5.2, [
    P(runs=[("Status banner: ", True), ("normal, fault predicted or fault detected.", False)], sz=15, bullet=True, sa=8),
    P(runs=[("Metrics: ", True), ("loss, latency, throughput, discards, errors, port status.", False)], sz=15, bullet=True, sa=8),
    P(runs=[("Objective 1: ", True), ("probability bar with the 0.22 threshold marker.", False)], sz=15, bullet=True, sa=8),
    P(runs=[("Objective 2: ", True), ("device, port, fault type, root cause, evidence.", False)], sz=15, bullet=True, sa=8),
    P(runs=[("Also: ", True), ("the network map with the affected device highlighted, and four history charts.", False)], sz=15, bullet=True, sa=12),
    P("Replays held-out test data, one minute per tick. Screenshot: CORE-R2.", sz=13, c=MUTED, sa=0, it=True),
], label="dash callouts")

# =============================================================== SLIDE 18: references
s = new_slide(17, "References", "References and tools",
              "These are the sources for the dataset, the methods and the related work. Thank you. We are happy to answer questions.", dark=True)
left_refs = [("Dataset", [
                "Singh, A., Gupta, R. LCORE-D: A Benchmark Dataset for Core Network Analysis. Mendeley Data, V2, 2025. doi:10.17632/77sztrg5ks.2 (CC BY 4.0)."]),
             ("LSTM and training", [
                "Hochreiter, S., Schmidhuber, J. Long Short-Term Memory. Neural Computation 9(8), 1997.",
                "Gers, F. A., Schmidhuber, J., Cummins, F. Learning to Forget: Continual Prediction with LSTM. Neural Computation 12(10), 2000.",
                "Srivastava, N. et al. Dropout: A Simple Way to Prevent Neural Networks from Overfitting. JMLR 15, 2014.",
                "Kingma, D., Ba, J. Adam: A Method for Stochastic Optimization. arXiv:1412.6980, 2014.",
                "An Explainable Failure Prediction Framework for Neural Networks in Radio Access Networks (LSTM). arXiv:2602.13231."])]
right_refs = [("Rule-based root cause analysis", [
                "Steinder, M., Sethi, A. S. A survey of fault localization techniques in computer networks. Science of Computer Programming 53(2), 165-194, 2004. doi:10.1016/j.scico.2004.01.010",
                "Valadarsky et al. Topology-based reasoning apparatus for root-cause analysis of network faults. US Patent 7,043,661, 2006.",
                "Using Rule Based Decision Trees for Automatic Passive Diagnostics of the Network Problems. Brno University of Technology, FIT."])]


def ref_paras(groups, start):
    out, n = [], start
    for gi, (head, items) in enumerate(groups):
        out.append(P(head, sz=14.5, b=True, c=TAN, sa=4))
        for j, it in enumerate(items):
            last = (gi == len(groups) - 1 and j == len(items) - 1)
            out.append(P(f"{n}.  {it}", sz=13, c=SAND, sa=0 if last else 7))
            n += 1
    return out, n


lp, nxt = ref_paras(left_refs, 1)
rp, _ = ref_paras(right_refs, nxt)
add_text(s, LM, 1.6, 5.95, 4.2, lp, label="refs left")
add_text(s, 6.78, 1.6, 5.95, 4.2, rp, label="refs right")
add_text(s, LM, 5.75, CW, 0.5, [P("Built with: Python, TensorFlow/Keras, scikit-learn, pandas, NetworkX, Flask, Chart.js. Data source simulated in GNS3.", sz=14, c=TAN, sa=0)], label="built with")
add_text(s, LM, 6.4, CW, 0.55, [P("Thank you. Questions?", sz=26, b=True, c=CREAM, sa=0, font=TITLE_FONT)], label="thanks")

for _suffix in ("", "_updated", "_v3", "_v4", "_v5"):
    _path = OUT.replace(".pptx", _suffix + ".pptx")
    try:
        prs.save(_path)
        OUT = _path
        break
    except PermissionError:
        continue
print("saved", OUT)
print("slides:", len(prs.slides))
print("fit warnings:", len(_fit_warnings))
for w in _fit_warnings: print("  -", w)
