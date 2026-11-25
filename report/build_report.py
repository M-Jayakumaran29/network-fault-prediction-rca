import os
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

os.chdir(os.path.dirname(os.path.abspath(__file__)))
FONT = "Times New Roman"
doc = Document()
st = doc.styles["Normal"]; st.font.name = FONT; st.font.size = Pt(10.5)
st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
sec = doc.sections[0]
sec.page_width, sec.page_height = Inches(8.5), Inches(11)
sec.left_margin = sec.right_margin = Inches(0.75); sec.top_margin = Inches(0.8); sec.bottom_margin = Inches(0.9)
L, C, R, J = WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.RIGHT, WD_ALIGN_PARAGRAPH.JUSTIFY


def fmt(p, align=J, before=0, after=4, first=None, keep=False):
    pf = p.paragraph_format; p.alignment = align
    pf.space_before = Pt(before); pf.space_after = Pt(after); pf.line_spacing = 1.05
    if first is not None: pf.first_line_indent = Inches(first)
    if keep: pf.keep_with_next = True
    return p


def run(p, text, b=False, i=False, size=None, sc=False, sup=False, sub=False):
    r = p.add_run(text); r.bold = b; r.italic = i; r.font.name = FONT
    r._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    if size: r.font.size = Pt(size)
    if sc: r.font.small_caps = True
    if sup: r.font.superscript = True
    if sub: r.font.subscript = True
    return r


def rich(p, text, size=None):
    import re
    for tok in re.split(r"(\*\*.+?\*\*|\*.+?\*|\^.+?\^|~.+?~)", text):
        if not tok: continue
        if tok.startswith("**"): run(p, tok[2:-2], b=True, size=size)
        elif tok.startswith("*"): run(p, tok[1:-1], i=True, size=size)
        elif tok.startswith("^"): run(p, tok[1:-1], sup=True, size=size)
        elif tok.startswith("~"): run(p, tok[1:-1], sub=True, size=size)
        else: run(p, tok, size=size)


def para(text, first=0.2, after=4):
    p = doc.add_paragraph(); fmt(p, first=first, after=after); rich(p, text); return p


ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII"]
cnt = {"sec": 0}


def H1(title):
    cnt["sec"] += 1
    p = doc.add_paragraph(); fmt(p, C, before=8, after=4, keep=True)
    run(p, f"{ROMAN[cnt['sec']-1]}. ", size=10); run(p, title.upper(), size=10)


def H1u(title):
    p = doc.add_paragraph(); fmt(p, C, before=8, after=4, keep=True); run(p, title.upper(), size=10)


def H2(letter, title):
    p = doc.add_paragraph(); fmt(p, L, before=4, after=2, keep=True)
    run(p, f"{letter}. {title}", i=True, size=10)


def bullets(items, num=False):
    for k, t in enumerate(items, 1):
        p = doc.add_paragraph(); fmt(p, after=2)
        p.paragraph_format.left_indent = Inches(0.25); p.paragraph_format.first_line_indent = Inches(-0.2)
        rich(p, (f"{k})  " if num else "•  ") + t)


def equation(expr, n):
    p = doc.add_paragraph(); fmt(p, L, before=2, after=4)
    ts = p.paragraph_format.tab_stops
    ts.add_tab_stop(Inches(1.7), WD_TAB_ALIGNMENT.CENTER); ts.add_tab_stop(Inches(3.4), WD_TAB_ALIGNMENT.RIGHT)
    run(p, "\t"); rich(p, expr); run(p, f"\t({n})")


def caption(text, n=0, table=False):
    if table:
        p = doc.add_paragraph(); fmt(p, C, before=6, after=1, keep=True)
        run(p, f"TABLE {ROMAN[n-1]}", size=8)
        p2 = doc.add_paragraph(); fmt(p2, C, after=3, keep=True); run(p2, text.upper(), size=8)
    else:
        p = doc.add_paragraph(); fmt(p, J, before=1, after=6)
        run(p, f"Fig. {n}. ", size=8); run(p, text, size=8)


def figure(path, width, cap, n):
    p = doc.add_paragraph(); fmt(p, C, before=2, after=1, keep=True)
    p.add_run().add_picture(path, width=Inches(width))
    caption(cap, n)


def shade(cell, color):
    tcPr = cell._element.get_or_add_tcPr(); s = OxmlElement("w:shd")
    s.set(qn("w:val"), "clear"); s.set(qn("w:color"), "auto"); s.set(qn("w:fill"), color); tcPr.append(s)


def borders(tbl):
    b = OxmlElement("w:tblBorders")
    for e in ("top", "bottom", "insideH"):
        x = OxmlElement(f"w:{e}"); x.set(qn("w:val"), "single"); x.set(qn("w:sz"), "4"); x.set(qn("w:color"), "444444"); b.append(x)
    tbl._element.tblPr.append(b)


def table(rows, widths, n, cap, fs=8, align=None):
    caption(cap, n=n, table=True)
    t = doc.add_table(rows=len(rows), cols=len(rows[0])); t.alignment = WD_TABLE_ALIGNMENT.CENTER; t.autofit = False
    borders(t)
    for r_i, row in enumerate(rows):
        for c_i, val in enumerate(row):
            c = t.cell(r_i, c_i); c.width = Inches(widths[c_i])
            p = c.paragraphs[0]; fmt(p, (align[c_i] if align else L), after=0)
            run(p, str(val), b=(r_i == 0), size=fs)
            if r_i < len(rows) - 1: p.paragraph_format.keep_with_next = True
            if r_i == 0: shade(c, "EFE6D6")
    sp = doc.add_paragraph(); fmt(sp, after=2); sp.paragraph_format.line_spacing = Pt(5)


# ============ TITLE BLOCK ============
p = doc.add_paragraph(); fmt(p, C, after=8)
run(p, "AI-Based Network Fault Prediction Using LSTM and Rule-Based Root Cause Analysis on the LCORE-D Dataset", b=True, size=20)
authors = [("Gopika Rajalal", "CB.SC.U4AIE25016"), ("Jayakumaran", "CB.SC.U4AIE25020"),
           ("Praveen", "CB.SC.U4AIE25030"), ("Mayookha Mahesh", "CB.SC.U4AIE25031")]
t = doc.add_table(rows=1, cols=4); t.alignment = WD_TABLE_ALIGNMENT.CENTER; t.autofit = False
for c, (nm, rid) in zip(t.rows[0].cells, authors):
    c.width = Inches(1.75)
    p = c.paragraphs[0]; fmt(p, C, after=0); run(p, nm, size=11)
    p2 = c.add_paragraph(); fmt(p2, C, after=0); run(p2, rid, size=10)
sp = doc.add_paragraph(); fmt(sp, after=6)

# ============ TWO-COLUMN BODY ============
body = doc.add_section(WD_SECTION.CONTINUOUS)
cols = OxmlElement("w:cols"); cols.set(qn("w:num"), "2"); cols.set(qn("w:space"), "360")
body._sectPr.append(cols)

p = doc.add_paragraph(); fmt(p, first=0)
run(p, "Abstract—", b=True, size=9)
rich(p, "This paper presents an AI-based network monitoring prototype built on LCORE-D, a public telemetry dataset recorded from an emulated internet-service-provider core network. The system has two objectives. Objective 1 is fault prediction: a Long Short-Term Memory (LSTM) network reads the previous ten one-minute observations of a device (six aggregated health indicators) and outputs the probability that the device will be in a non-healthy state in the next minute. Objective 2 is root cause analysis (RCA): when a fault is predicted, nine transparent, hand-written rules inspect the device metrics, its individual interfaces, its per-device healthy baseline and a topology graph, and return a structured diagnosis with evidence. On a chronologically held-out test split, the LSTM reaches 0.823 accuracy, 0.771 precision, 0.976 recall and 0.861 F1 at a validation-selected threshold of 0.22, against an F1 of 0.721 for a trivial always-fault predictor and 0.854 for a logistic-regression baseline on the same windows. Per-device analysis shows that most of the gain comes from separating chronically disturbed devices from nearly always healthy ones, rather than from timing individual faults. We also report a second negative finding: neither the rules nor a random-forest alternative can reliably name the specific fault type recorded in the dataset’s fault log, because almost every fault minute affects five to seven devices at once. A Flask and JavaScript dashboard replays the test split through the full pipeline. No result in this report is simulated or tuned on the test set.", size=9)

p = doc.add_paragraph(); fmt(p, first=0, after=6)
run(p, "Index Terms—", b=True, i=True, size=9)
run(p, "network fault prediction, LSTM, root cause analysis, rule-based systems, time-series classification, SNMP telemetry, LCORE-D", i=True, size=9)

# ---------- I ----------
H1("Introduction")
para("Modern service-provider networks generate a continuous stream of telemetry: link throughput, packet loss, response time, interface errors and discards, and the operational state of ports. Operators traditionally react after a threshold alarm fires and then spend considerable time working out which component actually failed. Two capabilities shorten this cycle. The first is *prediction*: raising a warning as a degradation develops. The second is *root cause analysis*: explaining which device or interface is most likely responsible, and why.")
para("This project builds both capabilities on LCORE-D, a public dataset of monitored devices in an emulated core network [1]. The work is organised around two objectives:")
bullets(["**Objective 1 – Fault prediction.** A sequence model (LSTM) predicts, one minute ahead, whether a device will be non-healthy.",
         "**Objective 2 – Root cause analysis.** A rule-based engine, with no machine learning, explains each predicted fault and returns the probable cause, the affected interface, the evidence and a coarse confidence level."], num=True)
para("An earlier plan also included a simulated self-healing stage. It was removed so that the two remaining objectives could be implemented, evaluated and explained properly; the removed code is archived and is not part of the results here.")
para("**Contributions.** (i) A leakage-safe preprocessing pipeline that turns seven raw per-device files into six aggregated indicators with gap-aware segmentation and a chronological split. (ii) A compact LSTM predictor whose decision threshold is chosen on validation data only. (iii) A transparent nine-rule RCA engine that uses a topology graph for shared-upstream reasoning. (iv) An end-to-end web dashboard. (v) An honest evaluation, including the limits of what rules and a learned alternative can infer from this dataset.")
para("Section II reviews related work, Section III describes the dataset, Section IV the system architecture, Section V the preprocessing, Section VI the LSTM predictor, Section VII the RCA engine, Section VIII the dashboard, Section IX the limitations, and Section X concludes.")

# ---------- II ----------
H1("Related Work")
H2("A", "Sequence models for fault prediction")
para("Recurrent networks process a sequence one step at a time while carrying a hidden state. Plain recurrent networks struggle to retain information over long spans, which motivated the Long Short-Term Memory cell of Hochreiter and Schmidhuber [2]. The LSTM adds a cell state protected by multiplicative gates, and Gers *et al.* later added the forget gate that lets the cell discard stale information [3]. These properties suit network telemetry, where a fault is often preceded by a drift in loss, latency or error counters over several minutes. Regularisation by dropout [4] and adaptive optimisation by Adam [5] are standard companions and are used in this work.")
H2("B", "Fault localisation and rule-based RCA")
para("Steinder and Sethi’s survey of fault localisation in computer networks [6] groups techniques into model-based, rule-based, case-based and probabilistic approaches and highlights the value of explicit dependency models. Rule-based systems remain attractive in operations because every conclusion can be traced to a named condition. Industrial work such as a topology-based reasoning apparatus for root-cause analysis [7] and academic work on rule-based decision trees for automatic passive diagnostics [8] follow the same idea: encode operator knowledge as conditions over measured metrics and over the dependency structure of the network.")
H2("C", "Alternative sequence models")
para("Gated recurrent units simplify the LSTM by merging gates [12], and temporal convolutional networks process sequences with dilated convolutions instead of recurrence [13]. Either could replace the LSTM in the proposed pipeline, and comparing them is listed as future work because the present study trained only the LSTM and two simple baselines.")
H2("D", "Positioning of this work")
para("We combine a learned predictor with a rule-based explainer. Prediction benefits from data-driven pattern recognition, whereas diagnosis benefits from auditable logic. We make no claim that this combination outperforms other published approaches; no controlled comparison against other architectures was run. The contribution is a complete, documented and reproducible pipeline together with a candid evaluation.")

# ---------- III ----------
H1("Dataset")
para("LCORE-D (Mendeley Data, version 2, DOI 10.17632/77sztrg5ks.2) was recorded from an internet-provider core network emulated in GNS3 [1]. Seven devices are monitored: six core routers (CORE-R1 to CORE-R6) and one edge device (EDGE-MS). Each device has one file of samples taken every 60 seconds, with one row per interface per sample and 51 raw columns covering ICMP probes, SNMP counters, interface state and topology descriptors. After aggregation to device level the dataset holds 169,712 device-minutes. A separate fault log lists induced fault events, of which 69 were usable after cleaning.")
para("Each sample carries a state label: **H** healthy, **T** transient, **F** fault, and a single **TH** row. In this work *any* non-healthy class (T, F or TH) is treated as the positive class “fault”, because transient disturbances are the dominant non-healthy state. Table I shows the resulting class balance.")
table([["Split", "Rows", "H", "T", "F", "% non-H"],
       ["Train", "135,316", "60,498", "73,423", "1,395", "55.3"],
       ["Validation", "25,142", "9,048", "15,239", "854", "64.0"],
       ["Test", "9,254", "4,047", "4,804", "373", "56.3"]],
      [0.65, 0.6, 0.55, 0.55, 0.45, 0.6], 1, "Class counts per chronological split (device-minutes)", align=[L] + [R] * 5)
para("Two properties of the data shape every later decision. First, the labels are roughly balanced between healthy and non-healthy, but “non-healthy” is dominated by transient (T) rows rather than hard faults (F). Second, the topology is *not* provided as an adjacency list; only per-device hop counts and a dependent-count descriptor are given, so the topology must be inferred (Section IV-B).")

H2("A", "Data-quality observations")
para("Inspection of the raw files, done before any modelling, revealed several issues that influenced the design. (i) Sampling is not continuous: each device’s record splits into about 50 contiguous segments separated by gaps, so windows must respect segment boundaries. (ii) Missing readings are encoded as the sentinel −1 rather than as empty cells. (iii) The *path_up* column is constant across the whole dataset and therefore carries no information, and the operational-status column almost never reports an explicit “down” value, so a missing or non-up reading has to serve as the down signal. (iv) SNMP availability equals 0 on 1,072 aggregated rows, but 429 of those rows are labelled healthy, so an unreachable agent is a strong but imperfect failure indicator. (v) The 51 columns describe interfaces, topology and measurement metadata, most of which are constant or redundant for health assessment.")
H2("B", "Fault log")
para("The fault log lists induced events with start and end times and a fault type (for example link failure, multiple-link failure, node failure, line-card failure, ICMP blocked by firewall, misconfiguration and routing misconfiguration). After removing entries that could not be aligned with the telemetry, 69 events remained. The log is used only for the RCA evaluation in Section VII-F; the LSTM is trained on the per-minute state labels.")

# ---------- IV ----------
H1("System Architecture")
H2("A", "Pipeline overview")
para("Fig. 1 shows the data path. Raw device files are loaded, normalised and aggregated; the LSTM converts each 10-minute window into a fault probability; a validation-tuned threshold turns it into a decision; and the RCA engine explains each positive decision. A Flask backend replays the held-out test split minute by minute and a browser dashboard presents the results.")
figure("fig/arch.png", 2.2, "Overall architecture of the two-objective system.", 1)
H2("B", "Inferred topology")
para("The dataset exposes three descriptors per device: hop distance to the core (*hop_to_core*), hop distance to the server (*hop_to_server*) and the number of downstream dependents. These are mutually consistent with a single tree: the server connects to EDGE-MS, then CORE-R1 (the core), CORE-R2 and CORE-R3 in a chain, after which CORE-R3 fans out to CORE-R4, CORE-R5 and CORE-R6 (Fig. 2). The graph is implemented with NetworkX and is used only for the shared-upstream reasoning of Section VII and for the dashboard’s topology view.")
figure("fig/topology.png", 3.3, "Topology inferred from hop counts (a best-effort reconstruction, not supplied by the dataset).", 2)
para("This reconstruction is a *best guess*. Downstream-dependent counts of up to 13 suggest that the emulated network contains more nodes than the seven that are monitored, and a real provider core is often a mesh with redundant paths that a tree cannot represent. All topology-based conclusions should be read with that caveat.")

# ---------- V ----------
H1("Data Preprocessing")
H2("A", "From 51 raw columns to six indicators")
para("Most raw columns are identifiers, constants or descriptors that do not vary with health. Six indicators were kept because they directly describe service quality and interface health and exist for every device (Table II).")
table([["Indicator", "Meaning (per device per minute)"],
       ["icmp_loss", "Percentage of ICMP probes lost"],
       ["icmp_response_time", "Mean ICMP round-trip time (ms)"],
       ["throughput_bps", "(bits in + bits out) / 60 s, summed over ports"],
       ["discards_total", "Packets dropped by interfaces, summed"],
       ["errors_total", "Damaged packets in and out, summed"],
       ["oper_status_up_frac", "Fraction of ports whose status is up"]],
      [1.35, 2.0], 2, "The six model input features")
H2("B", "Aggregation, cleaning and segmentation")
para("Raw rows are per interface, whereas the model predicts per device. Counters are therefore aggregated to device level by summation (throughput, discards, errors) or by the fraction of ports reporting “up”. The sentinel value −1, which marks a missing reading, is replaced by 0, and column names are normalised across the seven files. Sampling is nominally every 60 s but contains gaps. A gap larger than 60 s ends a *segment*, and windows are never built across a gap, so the LSTM never sees an artificial jump in time.")
H2("C", "Chronological split and scaling")
para("Random shuffling of time-series windows leaks information because adjacent windows overlap almost entirely. The data are instead split by time: the first 70% of the time range is used for training, the next 15% for validation and the last 15% for testing. Because the induced faults are not uniform in time, the resulting row shares are about 80%, 15% and 5.5% (135,316, 25,142 and 9,254 rows). A standard scaler (zero mean, unit variance) is fitted on the training rows only and then applied unchanged to validation, test and runtime data.")
H2("D", "Sliding windows")
para("For each device segment, a window of *W* = 10 consecutive minutes (10×6 values) forms one input, and the label is the class one step (*H* = 1 minute) after the window ends. This yields 132,714 training, 24,608 validation and 8,974 test windows. In the training windows 55.5% are positive, so no resampling was needed.")

# ---------- VI ----------
H1("Objective 1: LSTM Fault Predictor")
H2("A", "Why an LSTM")
para("A fault is rarely visible in a single sample; loss may climb, latency may drift and error counters may accumulate over several minutes. A model that reads the whole window and remembers what happened earlier is therefore a natural fit. At each step *t*, with input *x*~t~, previous hidden state *h*~t−1~ and previous cell state *c*~t−1~, the LSTM cell computes:")
equation("*f*~t~ = σ(*W*~f~[*h*~t−1~, *x*~t~] + *b*~f~)", 1)
equation("*i*~t~ = σ(*W*~i~[*h*~t−1~, *x*~t~] + *b*~i~)", 2)
equation("*c̃*~t~ = tanh(*W*~c~[*h*~t−1~, *x*~t~] + *b*~c~)", 3)
equation("*c*~t~ = *f*~t~ ⊙ *c*~t−1~ + *i*~t~ ⊙ *c̃*~t~", 4)
equation("*o*~t~ = σ(*W*~o~[*h*~t−1~, *x*~t~] + *b*~o~),  *h*~t~ = *o*~t~ ⊙ tanh(*c*~t~)", 5)
para("The *forget gate f* decides how much old memory to keep, the *input gate i* how much new information to write, and the *output gate o* how much of the memory to expose as the hidden state. The symbol σ is the logistic sigmoid and ⊙ is element-wise multiplication. After the tenth step, the final hidden state summarises the window.")
H2("B", "Network and training configuration")
para("The architecture is LSTM(64) → Dropout(0.3) → Dense(32, ReLU) → Dense(1, sigmoid). The 64 LSTM units are 64 parallel memory cells, each with its own gates; their weights are learned during training, while the number of units is fixed beforehand. Dropout randomly silences 30% of the 64 outputs during training so that the network cannot rely on a few units, which reduces over-fitting; it is inactive at prediction time. The final sigmoid outputs a probability *p* between 0 and 1. Training minimises binary cross-entropy,")
equation("*L* = −[ *y* log *p* + (1 − *y*) log(1 − *p*) ],", 6)
para("with the Adam optimiser [5] and early stopping. Table III lists the settings.")
table([["Setting", "Value"],
       ["Input window", "10 steps × 6 features"],
       ["Prediction horizon", "1 step (60 s ahead)"],
       ["LSTM units / dropout", "64 / 0.3"],
       ["Dense layer", "32 units, ReLU"],
       ["Optimiser / learning rate", "Adam / 0.001"],
       ["Batch size", "64"],
       ["Early stopping", "patience 6 on val. loss"],
       ["Epochs run / best val. loss", "8 / 0.299"],
       ["Random seed", "42"]],
      [1.75, 1.6], 3, "Model and training settings")
para("The network has 20,289 trainable parameters (18,176 in the LSTM layer, 2,080 in the dense layer and 33 in the output unit), which is small enough to train on a laptop CPU. A single-window forward pass took about 29 ms on the development machine (CPU only, Windows 11), far below the 60-second sampling interval, so the predictor could score all seven devices in real time.")
para("Training stopped after eight epochs because validation loss had stopped improving (best 0.299). Fig. 3 shows that training loss decreased only slightly (0.278 to 0.267) and validation loss was flat, so the model converges quickly without strong over-fitting; the validation AUC stays near 0.90 throughout.")
figure("fig/training.png", 3.3, "Training and validation loss (left) and AUC (right) over the eight epochs run.", 3)
H2("C", "Experimental protocol")
para("All experiments follow one protocol. Preprocessing and the scaler use training rows only; the model is trained on the training windows and monitored on the validation windows; the threshold is selected on validation; and the test windows are used once, for reporting. Windows that would straddle a split boundary are discarded so that no window overlaps two splits, and the random seed is fixed to 42 for NumPy and TensorFlow. The logistic-regression baseline of Section VI-F uses the same windows and the same validation-based threshold rule, which keeps the comparison fair.")
H2("D", "Threshold selection")
para("The network outputs a probability, and a threshold converts it into a decision. The threshold was chosen by scanning values from 0.05 to 0.95 on the **validation** set and keeping the one with the highest F1, which gave 0.22. The F1 score is the harmonic mean of precision *P* and recall *R*:")
equation("F1 = 2*PR* / (*P* + *R*)", 7)
para("A low threshold favours recall, which suits monitoring where a missed fault is costlier than a false alert. The choice is not delicate: a threshold of 0.30 gives the same F1 and 0.50 a nearly equal value on the validation data. The threshold is then frozen and applied to the test set, which is never used for tuning.")
H2("E", "Evaluation metrics and results")
para("Let TP, FP, TN and FN be the numbers of true positives, false positives, true negatives and false negatives, where “positive” means non-healthy. The reported metrics are")
equation("Acc = (TP + TN) / (TP + FP + TN + FN)", 8)
equation("*P* = TP / (TP + FP),  *R* = TP / (TP + FN)", 9)
equation("FPR = FP / (FP + TN)", 10)
para("Precision answers “when the model raises an alarm, how often is it right?”; recall answers “of all non-healthy periods, how many were caught?”; and FPR measures the false-alarm burden on healthy periods. The ROC-AUC is the probability that a randomly chosen non-healthy window receives a higher score than a randomly chosen healthy one; it does not depend on the threshold. Table IV and Figs. 4–6 give the validation and test results. On test, the model detects 4,938 of 5,058 non-healthy windows (recall 0.976) but also raises 1,468 false alarms among 3,916 healthy windows (false-positive rate 0.375).")
table([["Metric", "Validation", "Test"],
       ["Accuracy", "0.911", "0.823"],
       ["Precision", "0.891", "0.771"],
       ["Recall", "0.982", "0.976"],
       ["F1", "0.934", "0.861"],
       ["False-positive rate", "0.217", "0.375"],
       ["ROC-AUC", "0.899", "0.820"]],
      [1.5, 0.95, 0.9], 4, "LSTM results at threshold 0.22", align=[L, R, R])
figure("fig/confusion.png", 3.3, "Confusion matrices at threshold 0.22 (validation and test windows).", 4)
figure("fig/metrics.png", 3.3, "Validation versus test metrics.", 5)
figure("fig/roc.png", 2.6, "ROC curve of the LSTM on the test windows (AUC 0.820).", 6)
H2("F", "Baselines and interpretation")
para("A fair evaluation needs references. Table V compares the LSTM with three baselines on the same 8,974 test windows. *Always-fault* predicts the positive class every time. *Persistence* copies the current state of the device to the next minute; it needs the ground-truth label of the present minute, which a deployed monitor does not have, so it is an upper-reference rather than a competitor. *Logistic regression* is a linear model fitted on the training windows (flattened 10×6 inputs, threshold chosen on validation).")
table([["Method", "Acc.", "Prec.", "Recall", "F1"],
       ["Always-fault", "0.564", "0.564", "1.000", "0.721"],
       ["Logistic regression", "0.812", "0.759", "0.976", "0.854"],
       ["LSTM (this work)", "0.823", "0.771", "0.976", "0.861"],
       ["Persistence (needs label)", "0.949", "0.955", "0.954", "0.955"]],
      [1.55, 0.45, 0.45, 0.5, 0.4], 5, "Test-set comparison with baselines", align=[L, R, R, R, R])
para("Three conclusions follow. First, the LSTM clearly improves on the always-fault predictor (F1 0.861 versus 0.721). Second, the improvement over the linear baseline is small (F1 +0.007, AUC 0.820 versus 0.800), so on this dataset the recurrent structure adds little beyond what the six indicators carry linearly. Third, knowing the current state is far more informative (F1 0.955) than what the LSTM extracts from the metrics, because non-healthy periods are long and persistent.")
H2("G", "Where does the skill come from? Per-device analysis")
para("Table VI and Fig. 7 break the test result down by device. CORE-R1 and EDGE-MS are almost always healthy (non-healthy in only 1.8% of all their minutes), whereas CORE-R2 to CORE-R6 are non-healthy 77–80% of the time. On CORE-R2 to CORE-R6 the LSTM flags essentially every window (recall 0.999–1.000 and precision equal to the base rate), and on CORE-R1 and EDGE-MS it flags none of the 56 and 62 positive windows (recall 0). The model therefore behaves largely as a *device-level* classifier: it has learned which devices are chronically disturbed, and the overall F1 gain over the always-fault predictor comes from correctly leaving the two healthy devices alone. It does not demonstrate fine-grained timing of individual faults within a device.")
table([["Device", "Windows", "Non-healthy", "Precision", "Recall", "F1"],
       ["CORE-R1", "1,280", "56", "0.000", "0.000", "0.000"],
       ["CORE-R2", "1,282", "1,020", "0.796", "1.000", "0.886"],
       ["CORE-R3", "1,282", "994", "0.775", "0.999", "0.873"],
       ["CORE-R4", "1,283", "976", "0.761", "1.000", "0.864"],
       ["CORE-R5", "1,280", "967", "0.755", "0.999", "0.860"],
       ["CORE-R6", "1,281", "983", "0.767", "1.000", "0.868"],
       ["EDGE-MS", "1,286", "62", "0.000", "0.000", "0.000"]],
      [0.7, 0.6, 0.75, 0.6, 0.5, 0.45], 6, "Test results per device at threshold 0.22", fs=7.5, align=[L, R, R, R, R, R])
figure("fig/perdevice.png", 3.3, "Share of non-healthy test windows per device and LSTM recall on each device.", 7)
H2("H", "Threshold sensitivity")
para("Table VII shows validation and test F1 for several thresholds, computed after training for transparency only; the operating point 0.22 was fixed from the validation column before the test set was examined. The curve is almost flat between 0.10 and 0.60 on both sets (test F1 0.857–0.861), which confirms that the exact threshold matters little and that the probabilities are close to a device-level score.")
table([["Threshold", "Val. F1", "Val. recall", "Test F1", "Test recall"],
       ["0.10", "0.931", "0.983", "0.859", "0.977"],
       ["0.22", "0.934", "0.982", "0.861", "0.976"],
       ["0.30", "0.934", "0.981", "0.861", "0.975"],
       ["0.40", "0.933", "0.978", "0.860", "0.972"],
       ["0.50", "0.932", "0.974", "0.859", "0.969"],
       ["0.60", "0.930", "0.971", "0.857", "0.966"]],
      [0.75, 0.6, 0.7, 0.6, 0.7], 7, "Sensitivity of F1 and recall to the threshold", fs=7.5, align=[L, R, R, R, R])
para("These figures describe *non-healthy* prediction, which is dominated by transient rows. They should not be read as the accuracy of predicting the 69 hard-fault events; the test split contains only a few such events, so a per-event evaluation would be statistically weak.")

# ---------- VII ----------
H1("Objective 2: Rule-Based RCA")
H2("A", "Design principles")
para("RCA is triggered whenever the LSTM predicts a fault. No machine learning is used in this stage. Each rule is a short function over the device’s current metrics, its interface-level counters, a healthy baseline and the topology graph. A rule returns a finding with a probable fault type, an evidence sentence and a weight; the weight is an evidence strength, not a probability. The baseline of each metric is the per-device median over *healthy training rows only*, so “normal” is defined separately for every device.")
H2("B", "The nine rules")
table([["#", "Rule", "Fires when", "Fault type", "W"],
       ["1", "SNMP unreachable", "SNMP availability = 0", "node failure", "4"],
       ["2", "Interface down", "port up-fraction < 1", "link / multi-link", "3"],
       ["3", "Localised errors", "one port errors > max(5, 5×base); others ≤ 20% of it", "line-card failure", "3"],
       ["4", "Discards spike", "discards > max(5, 5×base)", "link failure", "2"],
       ["5", "Severe ICMP loss", "loss ≥ 80%", "link failure", "3"],
       ["6", "ICMP blocked", "loss ≥ 30%, SNMP ok, clean counters", "ICMP blocked", "2"],
       ["7", "Latency anomaly", "RTT > 3× base, loss < 30%, clean errors", "routing misconfig.", "2"],
       ["8", "Shared upstream", "≥ 2 devices faulty; common ancestor not SERVER", "node / multi-link", "4"],
       ["9", "Transient fallback", "no other rule fired", "transient", "1"]],
      [0.2, 0.95, 1.2, 0.7, 0.22], 8, "Rules, trigger conditions, outputs and weights (W)", fs=7,
      align=[C, L, L, L, C])
para("Rules 1–2 read direct signals from SNMP [9]: whether the agent answers and whether each port’s operational status is up. Rules 3–4 use error and discard counters, where an error is a damaged packet and a discard is a packet dropped without being damaged, typically from congestion. Rules 5–6 separate a real link failure (very high loss) from ICMP-only blocking, in which loss is high although SNMP answers and counters are clean. Rule 7 detects a latency rise without loss, which is consistent with a path change. Rule 8 performs topology reasoning: if several devices are abnormal in the same minute, the lowest common ancestor of all of them in the topology graph is blamed instead of each device individually. Rule 9 is a weak catch-all.")
para("To make the rules concrete, four *illustrative* cases (constructed for explanation, not measured events) are given. (a) If SNMP on a router stops answering while its ICMP loss is 100%, rule 1 (weight 4) and rule 5 (weight 3) both fire; the highest weight wins and the diagnosis is node failure. (b) If one of five ports shows 40 errors while the others show 0–2 and the device baseline is 1 error, rule 3 fires with weight 3 and names that port as the affected interface, pointing to a localised hardware problem. (c) If ICMP loss is 60% but SNMP answers and error and discard counters are at baseline, rule 6 fires and the engine reports ICMP blocking rather than a link failure, since a dead link would also silence SNMP. (d) If response time is four times the baseline while loss is 2% and counters are clean, rule 7 fires and suggests a path change.")
H2("C", "Decision procedure and confidence")
figure("fig/rcaflow.png", 2.3, "Flow of the rule-based RCA engine.", 8)
para("All rules are evaluated, the findings are sorted by weight, and the highest-weight finding becomes the primary diagnosis; ties go to the earlier rule. The other triggered rules are returned as supporting evidence. A coarse confidence label is derived from the summed weight *S*: “high” for *S* ≥ 6, “medium” for 3 ≤ *S* < 6, otherwise “low”. It is explicitly labelled a rule-based evidence level and not an ML probability. The structured output contains the affected device and interface, the probable fault type, the root-cause device, the evidence list, the triggered rules and the confidence.")
H2("D", "Worked example")
para("Suppose CORE-R2 is predicted faulty while CORE-R3 to CORE-R6 are also abnormal in the same minute and SNMP on CORE-R2 does not answer. Rule 1 fires (weight 4, node failure) and rule 8 fires (weight 4), since the lowest common ancestor of the five devices is CORE-R2. The weights sum to 8, so the confidence is high; the tie is resolved in favour of the earlier rule, and the report names CORE-R2 as the root cause with both pieces of evidence attached. This is the situation shown in the dashboard screenshot (Fig. 9).")
para("The engine returns one structured record per predicted fault. For the case above its fields are: *fault_detected* = true; *affected_device* = CORE-R2; *affected_interface* = the port with the largest error and discard count; *probable_fault_type* = node_failure; *root_cause* = CORE-R2 (shared_upstream_component); *root_cause_device* = CORE-R2; *evidence* = one sentence per triggered rule; *triggered_rules* = [snmp_unreachable, shared_upstream_component, …]; and *confidence* = high (a rule-based evidence level, not an ML probability).")
H2("E", "Topology reasoning in rule 8")
para("Rule 8 turns simultaneous anomalies into a single suspect by walking up the inferred tree. Table IX lists, for several sets of simultaneously abnormal devices, the common ancestor computed by the implemented graph routine. When one device fails high in the tree, every device below it becomes unreachable, so the whole group points to the ancestor; when the ancestor is the server itself, the rule abstains because no device can be singled out.")
table([["Abnormal devices", "Blamed device"],
       ["CORE-R4, CORE-R5", "CORE-R3"],
       ["CORE-R4, CORE-R5, CORE-R6", "CORE-R3"],
       ["CORE-R3, CORE-R6", "CORE-R3"],
       ["CORE-R1, CORE-R4", "CORE-R1"],
       ["EDGE-MS, CORE-R3", "EDGE-MS"],
       ["CORE-R2 to CORE-R6 (all five)", "CORE-R2"]],
      [2.2, 1.1], 9, "Common-ancestor results used by rule 8", fs=7.5)
H2("F", "How accurate is the diagnosis? An honest assessment")
para("We tested whether the diagnosed fault *type* agrees with the type recorded in the dataset’s fault log, using 382 held-out minutes belonging to 7 fault events. The rules agree on 41% of those minutes. However, always guessing the most common type would give 43%, so the rules do **not** beat a naive guess; their 41% is largely an artifact of one label being common. To check whether learning could do better, we trained Naive Bayes and random-forest classifiers [11] on the same signals; the random forest (selected on validation) scored 31% accuracy on the held-out minutes, and 22% in grouped cross-validation against a 19% majority baseline. Learning therefore does not solve the problem either.")
table([["Method", "Held-out minutes", "Grouped CV"],
       ["Nine rules (type agreement)", "41%", "–"],
       ["Majority-type guess", "43%", "19%"],
       ["Random forest", "31%", "22%"]],
      [1.5, 1.0, 0.85], 10, "Agreement with fault-log type (382 held-out minutes, 7 events)", fs=7.5, align=[L, R, R])
para("The reason is structural. During a logged fault, five to seven of the seven devices are abnormal at the same time, so rule 8 decides about 96% of the diagnoses on real fault rows, and the individual-device signals that would distinguish, for example, a line-card failure from a link failure are masked. In addition, SNMP availability is 0 on 1,072 rows, of which 429 are labelled healthy, which weakens rule 1 as a pure node-failure indicator. We conclude that this dataset supports explaining *where* and *which signals* (the evidence), but not reliably naming the exact fault type, and we present the RCA output in that light. An attempt to adjust rules 5, 6 and 8 reduced agreement with the log and was reverted; the original rule set is the one evaluated here.")

# ---------- VIII ----------
H1("Dashboard and Implementation")
para("The backend is a Flask application that loads the trained model [10], scaler and threshold and a replay engine. For a chosen device it steps through the chronological test rows one minute at a time. At each step it builds the latest 10×6 window, obtains the fault probability, compares it with the threshold and, if positive, gathers the device’s interface rows and the other devices that are non-healthy at the same timestamp (taken from the recorded labels, a documented simplification that avoids running the LSTM on all seven devices every tick), and calls the RCA engine. The front end polls the API and shows the status banner (NORMAL, FAULT_PREDICTED or FAULT_DETECTED), a probability bar with the threshold marker, live metric tiles, the RCA panel with evidence, the topology view with affected nodes highlighted, and history charts.")
para("Table XI lists the REST endpoints, and the implementation uses Python 3.10 with TensorFlow/Keras 2.19 [10], scikit-learn 1.7 [11], pandas, NumPy, NetworkX and Flask 3.1 on the server, and plain JavaScript with Chart.js charts in the browser.")
table([["Endpoint", "Method", "Purpose"],
       ["/api/health", "GET", "Model and engine readiness"],
       ["/api/devices", "GET", "Monitored devices"],
       ["/api/topology", "GET", "Inferred topology graph"],
       ["/api/state", "GET", "Current replay state"],
       ["/api/tick", "POST", "Advance one minute: predict, run RCA"],
       ["/api/reset", "POST", "Restart replay for a device"]],
      [1.1, 0.6, 1.65], 11, "Backend API", fs=7.5, align=[L, C, L])
figure("../presentation/assets/dashboard.png", 3.3, "Dashboard replaying device CORE-R2: status, probability, RCA evidence and topology.", 9)
para("The code is modular: *preprocessing/* (loading, features, scaling), *fault_prediction/* (windows, training, evaluation, inference), *rca/* (topology, rules, orchestrator), *backend/* (replay engine, API) and *frontend/*. All settings (window, horizon, split fractions, units, dropout, seed) live in one configuration file. Because the dashboard replays the held-out test split, what it shows is genuine out-of-sample behaviour of the trained model.")

# ---------- IX ----------
H1("Discussion and Limitations")
H2("A", "Limitations")
bullets(["**Positive class is mostly transient.** About 54% of all device-minutes are transient (T) and only about 1.3% are hard faults (F), so the headline metrics mostly measure disturbed-versus-healthy discrimination.",
         "**Device-level skill.** The LSTM flags almost every window on the five chronically disturbed devices and none of the positives on the two healthy ones (Section VI-G), and it improves only marginally on logistic regression (F1 0.861 versus 0.854).",
         "**Generalisation gap.** F1 falls from 0.934 (validation) to 0.861 (test) and the false-positive rate rises from 0.217 to 0.375; the test period is short (9,254 rows) and taken from the end of the recording.",
         "**Single emulated network.** The data come from one GNS3 emulation, so transfer of the trained model to other networks is unknown.",
         "**Inferred topology.** The tree is reconstructed from hop counts; the real network may be larger or meshed.",
         "**RCA cannot name the fault type reliably.** See Section VII-F: agreement with the fault log (41%) does not exceed a majority guess (43%).",
         "**Simplified replay.** Concurrent faulty devices come from recorded labels rather than from the LSTM, and the system replays data rather than connecting to a live network.",
         "**Limited model comparison.** Apart from the always-fault and logistic-regression baselines, no other sequence model (GRU, 1-D CNN, Transformer) was trained for Objective 1."])
para("These limitations suggest follow-up work: evaluating per fault event rather than per minute, comparing against GRU and gradient-boosting models, adding within-device features such as rates of change, using a longer recording or several networks, and replacing the inferred topology with a verified one.")
H2("B", "Practical considerations")
para("*Alarm fatigue.* With a false-positive rate of 0.375 on healthy windows, an operator would receive many alerts on devices that are in fact disturbed for long stretches. A deployment would need alert suppression, for example reporting only the first alarm per episode, and a higher threshold on devices known to be calm. *Human in the loop.* Because the RCA output is evidence-based but cannot name the fault type reliably, it should be presented as a ranked explanation for an engineer to verify, not as an automatic trigger for remediation. *Retraining.* Healthy baselines and scaler statistics are tied to the recorded period; a production system would recompute them periodically and monitor for drift.")

# ---------- X ----------
H1("Conclusion")
para("We built a two-objective system on the LCORE-D dataset. A small LSTM, fed with ten minutes of six aggregated indicators, predicts one minute ahead whether a device will be non-healthy, reaching an F1 of 0.861 and a recall of 0.976 on a chronologically held-out test set at a validation-chosen threshold of 0.22, and outperforming an always-fault predictor (F1 0.721), although only marginally a logistic-regression baseline (F1 0.854); per-device analysis shows that its skill is mainly device-level rather than minute-level timing of faults. A transparent nine-rule engine explains each predicted fault with evidence, a topology-aware root-cause device and a coarse confidence. Our honest evaluation shows that exact fault-type naming remains unreliable with the available data, whether rules or learning are used. The work is delivered with a full pipeline and a dashboard that replays genuine out-of-sample data.")

# ---------- APPENDICES ----------
H1u("Appendix A: Reproduction Steps")
bullets(["Place the LCORE-D files under *data/LCORE-D/*.",
         "Run preprocessing to create *device_features.csv* and the scaler (fitted on training rows only).",
         "Train the LSTM, then run evaluation, which selects the threshold on validation data and writes *threshold.json* and the figures.",
         "Start the backend (*backend/app.py*), open the dashboard in a browser, choose a device and press play."], num=True)
H1u("Appendix B: Notes on Reported Numbers")
para("All figures and tables are generated from the repository’s own output files (threshold and metrics file, training history and RCA report). Row counts per split come from the processed feature table. The always-fault baseline was computed from the test confusion matrix (4,938 + 120 positives and 2,448 + 1,468 negatives). The topology figure and rule table reflect the code at the time of writing.")

H1u("Appendix C: Glossary of Network Terms")
table([["Term", "Meaning"],
       ["ICMP", "Control protocol used by ping; yields loss and response time"],
       ["SNMP", "Protocol for reading device counters and port status"],
       ["Packet loss", "Share of probe packets that never get a reply"],
       ["Latency / RTT", "Time for a probe to reach a device and return"],
       ["Throughput", "Data actually carried per second, in bits per second"],
       ["Error", "A packet damaged in transit (bad checksum, etc.)"],
       ["Discard", "A healthy packet deliberately dropped, e.g. full queue"],
       ["Oper. status", "Whether a port is currently up or down"],
       ["Hop", "One router-to-router step along a path"]],
      [0.95, 2.4], 12, "Network terms used in this paper", fs=7.5)
H1u("Appendix D: Configuration Values")
table([["Parameter", "Value"],
       ["WINDOW_SIZE / PREDICTION_HORIZON", "10 steps / 1 step"],
       ["Sampling interval / max gap", "60 s / 60 s"],
       ["Split fractions (time range)", "0.70 / 0.15 / 0.15"],
       ["LSTM_UNITS / DENSE_UNITS", "64 / 32"],
       ["DROPOUT_RATE", "0.3"],
       ["BATCH_SIZE / MAX_EPOCHS", "64 / 60"],
       ["EARLY_STOPPING_PATIENCE", "6"],
       ["LEARNING_RATE", "0.001"],
       ["Threshold (validation F1)", "0.22"],
       ["Severe / moderate ICMP loss", "80% / 30%"],
       ["Latency spike factor", "3× baseline"],
       ["Error / discard spike", "5× baseline, floor 5"],
       ["RANDOM_SEED", "42"]],
      [2.1, 1.25], 13, "Main configuration values", fs=7.5)

# ---------- REFERENCES ----------
H1u("References")
refs = [
    "A. Singh and R. Gupta, “LCORE-D: A benchmark dataset for core network analysis,” Mendeley Data, v2, 2025, doi: 10.17632/77sztrg5ks.2 (CC BY 4.0).",
    "S. Hochreiter and J. Schmidhuber, “Long short-term memory,” *Neural Comput.*, vol. 9, no. 8, pp. 1735–1780, 1997.",
    "F. A. Gers, J. Schmidhuber, and F. Cummins, “Learning to forget: Continual prediction with LSTM,” *Neural Comput.*, vol. 12, no. 10, pp. 2451–2471, 2000.",
    "N. Srivastava, G. Hinton, A. Krizhevsky, I. Sutskever, and R. Salakhutdinov, “Dropout: A simple way to prevent neural networks from overfitting,” *J. Mach. Learn. Res.*, vol. 15, pp. 1929–1958, 2014.",
    "D. P. Kingma and J. Ba, “Adam: A method for stochastic optimization,” arXiv:1412.6980, 2014.",
    "M. Steinder and A. S. Sethi, “A survey of fault localization techniques in computer networks,” *Sci. Comput. Program.*, vol. 53, no. 2, pp. 165–194, 2004, doi: 10.1016/j.scico.2004.01.010.",
    "Valadarsky *et al.*, “Topology-based reasoning apparatus for root-cause analysis of network faults,” U.S. Patent 7,043,661, 2006.",
    "“Using rule based decision trees for automatic passive diagnostics of the network problems,” Faculty of Information Technology, Brno Univ. of Technology.",
    "J. Case, M. Fedor, M. Schoffstall, and J. Davin, “A simple network management protocol (SNMP),” RFC 1157, IETF, 1990.",
    "M. Abadi *et al.*, “TensorFlow: A system for large-scale machine learning,” in *Proc. 12th USENIX Symp. Operating Syst. Design Implement.*, 2016, pp. 265–283.",
    "F. Pedregosa *et al.*, “Scikit-learn: Machine learning in Python,” *J. Mach. Learn. Res.*, vol. 12, pp. 2825–2830, 2011.",
    "K. Cho *et al.*, “Learning phrase representations using RNN encoder–decoder for statistical machine translation,” in *Proc. EMNLP*, 2014, pp. 1724–1734.",
    "S. Bai, J. Z. Kolter, and V. Koltun, “An empirical evaluation of generic convolutional and recurrent networks for sequence modeling,” arXiv:1803.01271, 2018.",
]
for k, r in enumerate(refs, 1):
    p = doc.add_paragraph(); fmt(p, after=2)
    p.paragraph_format.left_indent = Inches(0.3); p.paragraph_format.first_line_indent = Inches(-0.3)
    rich(p, f"[{k}]  {r}", size=8)

# page-number footer (section 0; later sections inherit)
fp = sec.footer.paragraphs[0]; fp.alignment = C
for t_, txt in (("begin", None), (None, "PAGE"), ("end", None)):
    r = fp.add_run(); r.font.size = Pt(9)
    if t_:
        e = OxmlElement("w:fldChar"); e.set(qn("w:fldCharType"), t_)
    else:
        e = OxmlElement("w:instrText"); e.set(qn("xml:space"), "preserve"); e.text = txt
    r._r.append(e)
doc.core_properties.title = "AI-Based Network Fault Prediction Using LSTM and Rule-Based Root Cause Analysis"
doc.core_properties.author = "G. Rajalal, Jayakumaran, Praveen, M. Mahesh"
doc.save("REPORT_Network_Fault_Prediction_RCA.docx"); print("saved")
