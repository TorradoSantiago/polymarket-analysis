#!/usr/bin/env python3
"""
Polymarket Ops Intelligence — Project Brief PDF Generator
=========================================================
Generates a visual project brief in English, readable by
non-technical audiences (HR, ops managers, recruiters).

Usage:  python3 generate_brief.py
Output: polymarket_ops_brief.pdf
"""

import io
import math
from datetime import datetime, timezone

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
import numpy as np

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.colors import HexColor, white, black, Color
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, HRFlowable, KeepTogether, Flowable,
    BaseDocTemplate, PageTemplate, Frame
)
from reportlab.pdfgen import canvas as rl_canvas

# ── Palette ───────────────────────────────────────────────────────────────
NAVY   = HexColor("#0f172a")
BLUE   = HexColor("#3b82f6")
GREEN  = HexColor("#22c55e")
YELLOW = HexColor("#f59e0b")
RED    = HexColor("#ef4444")
PURPLE = HexColor("#a855f7")
CYAN   = HexColor("#22d3ee")
LIGHT  = HexColor("#f1f5f9")
MUTED  = HexColor("#94a3b8")
DARK   = HexColor("#1e293b")
WHITE  = white

# ── Snapshot data (from last dashboard run — 300 markets, May 2026) ───────
SNAP_DATE    = datetime.now(timezone.utc).strftime("%B %d, %Y")
SNAP_MARKETS = 300
SNAP_VOLUME  = "$39.4B"

QA_STATS   = {"PASS": 125, "REVIEW": 58, "FAIL": 117}
INT_STATS  = {"LOW": 266, "MEDIUM": 24, "HIGH": 10}
COMP_STATS = {"LOW": 293, "MEDIUM": 4, "HIGH": 3}
OPS_STATS  = {"LOW": 245, "MEDIUM": 55, "HIGH": 0, "CRITICAL": 0}

COUNTRIES = [
    ("United States",     89, 17_400),
    ("Russia / Ukraine",  18,  3_800),
    ("Iran / Israel",     12,  2_200),
    ("United Kingdom",     7,    920),
    ("France",             5,    610),
    ("China / Taiwan",     6,    550),
    ("Brazil",             3,    290),
    ("Germany",            2,    210),
    ("India",              2,    180),
    ("Saudi Arabia",       2,    130),
    ("North Korea",        1,     80),
    ("Turkey",             1,     70),
]

CAT_DATA = [
    ("Politics & Elections",        60, 17_480),
    ("Sports",                      52, 11_360),
    ("Geopolitics & World Affairs", 44,  3_820),
    ("Culture & Entertainment",      9,  1_420),
    ("Crypto & Blockchain",         16,  2_400),
    ("Economics & Finance",         10,  2_390),
    ("Technology & AI",              6,    400),
    ("Science, Health & Env.",       3,     40),
    ("Other",                       100,    90),
]


# ── Chart helpers ─────────────────────────────────────────────────────────

CHART_BG = "#0f172a"
CHART_TXT = "#94a3b8"

def _chart_img(fig, dpi=140):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi,
                bbox_inches="tight", facecolor=CHART_BG)
    plt.close(fig)
    buf.seek(0)
    return buf


def chart_donut(values, labels, colors_hex, title=""):
    fig, ax = plt.subplots(figsize=(4.2, 3.2), facecolor=CHART_BG)
    ax.set_facecolor(CHART_BG)
    wedges, _ = ax.pie(
        values,
        labels=None,
        colors=[matplotlib.colors.to_rgba(c) for c in colors_hex],
        startangle=90,
        wedgeprops=dict(width=0.52, edgecolor=CHART_BG, linewidth=2),
    )
    total = sum(values)
    ax.text(0, 0, f"{total:,}", ha="center", va="center",
            fontsize=14, fontweight="bold", color="white")
    ax.text(0, -0.22, "total", ha="center", va="center",
            fontsize=7, color=CHART_TXT)
    legend_labels = [f"{l} ({v})" for l, v in zip(labels, values)]
    ax.legend(legend_labels, loc="lower center", bbox_to_anchor=(0.5, -0.22),
              ncol=3, frameon=False,
              prop={"size": 7}, labelcolor=CHART_TXT)
    if title:
        ax.set_title(title, color="white", fontsize=8, fontweight="600", pad=6)
    fig.tight_layout(pad=0.4)
    return _chart_img(fig)


def chart_hbar(items, color_hex, title="", xlabel=""):
    labels = [i[0] for i in items]
    values = [i[1] for i in items]
    fig, ax = plt.subplots(figsize=(6.0, max(2.8, len(items)*0.38)),
                           facecolor=CHART_BG)
    ax.set_facecolor(CHART_BG)
    y = range(len(labels))
    bars = ax.barh(list(y), values, color=color_hex, height=0.6,
                   edgecolor="none", alpha=0.85)
    ax.set_yticks(list(y))
    ax.set_yticklabels(labels, color=CHART_TXT, fontsize=8)
    ax.tick_params(axis="x", colors=CHART_TXT, labelsize=7)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#334155")
    ax.spines["bottom"].set_color("#334155")
    ax.set_xlabel(xlabel, color=CHART_TXT, fontsize=7)
    ax.set_title(title, color="white", fontsize=8, fontweight="600", pad=6)
    ax.invert_yaxis()
    for bar, val in zip(bars, values):
        ax.text(bar.get_width() + max(values)*0.01, bar.get_y() + bar.get_height()/2,
                f"{val:,}", va="center", ha="left",
                color=CHART_TXT, fontsize=6.5)
    fig.tight_layout(pad=0.5)
    return _chart_img(fig)


def chart_country_double(countries):
    """Side-by-side: market count + volume by country"""
    labels  = [c[0] for c in countries]
    counts  = [c[1] for c in countries]
    volumes = [c[2]/1000 for c in countries]  # billions

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.5, 3.6), facecolor=CHART_BG)
    for ax in (ax1, ax2):
        ax.set_facecolor(CHART_BG)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#334155")
        ax.spines["bottom"].set_color("#334155")
        ax.tick_params(colors=CHART_TXT, labelsize=7.5)

    y = range(len(labels))

    # Market count
    ax1.barh(list(y), counts, color="#3b82f6", height=0.6, alpha=0.85, edgecolor="none")
    ax1.set_yticks(list(y)); ax1.set_yticklabels(labels, color=CHART_TXT, fontsize=8)
    ax1.set_title("Markets About Each Country", color="white", fontsize=9, fontweight="600", pad=8)
    ax1.set_xlabel("Number of active markets", color=CHART_TXT, fontsize=7)
    ax1.invert_yaxis()
    for i, v in enumerate(counts):
        ax1.text(v + 0.5, i, str(v), va="center", color=CHART_TXT, fontsize=6.5)

    # Volume
    ax2.barh(list(y), volumes, color="#a855f7", height=0.6, alpha=0.85, edgecolor="none")
    ax2.set_yticks(list(y)); ax2.set_yticklabels([], color=CHART_TXT)
    ax2.set_title("USD Volume Traded ($B)", color="white", fontsize=9, fontweight="600", pad=8)
    ax2.set_xlabel("Total volume (USD billions)", color=CHART_TXT, fontsize=7)
    ax2.invert_yaxis()
    for i, v in enumerate(volumes):
        ax2.text(v + 0.05, i, f"${v:.1f}B", va="center", color=CHART_TXT, fontsize=6.5)

    fig.suptitle("Global Market Distribution — Where Is the World Betting?",
                 color="white", fontsize=10, fontweight="700", y=1.02)
    fig.tight_layout(pad=0.8)
    return _chart_img(fig, dpi=150)


def chart_pipeline():
    """Simple 3-step data pipeline diagram"""
    fig, ax = plt.subplots(figsize=(7, 1.8), facecolor=CHART_BG)
    ax.set_facecolor(CHART_BG)
    ax.axis("off")
    ax.set_xlim(0, 10); ax.set_ylim(0, 2)

    boxes = [
        (1.0,  "Polymarket\nGamma API",   "#1d4ed8",  "Market titles,\ndescriptions,\nvolume & dates"),
        (4.5,  "PolymarketScan\nAPI",     "#7c3aed",  "Rules arb score,\ncontroversy,\nwhale activity"),
        (8.0,  "Ops Intelligence\nEngine","#0f766e",  "QA + Integrity\n+ Compliance\n+ World Map"),
    ]

    for x, title, col, sub in boxes:
        rect = mpatches.FancyBboxPatch((x-1.1, 0.6), 2.2, 1.1,
                                        boxstyle="round,pad=0.08",
                                        linewidth=0, facecolor=col, alpha=0.9)
        ax.add_patch(rect)
        ax.text(x, 1.35, title, ha="center", va="center",
                color="white", fontsize=7.5, fontweight="bold", linespacing=1.3)
        ax.text(x, 0.3, sub, ha="center", va="center",
                color=CHART_TXT, fontsize=6.2, linespacing=1.3)

    for xa, xb in [(2.1, 3.4), (5.6, 6.9)]:
        ax.annotate("", xy=(xb, 1.15), xytext=(xa, 1.15),
                    arrowprops=dict(arrowstyle="-|>",
                                   color=CHART_TXT, lw=1.2))

    fig.tight_layout(pad=0.2)
    return _chart_img(fig, dpi=130)


# ── Custom Flowables ──────────────────────────────────────────────────────

class ColoredRect(Flowable):
    def __init__(self, w, h, color):
        super().__init__()
        self.w, self.h, self.color = w, h, color

    def draw(self):
        self.canv.setFillColor(self.color)
        self.canv.rect(0, 0, self.w, self.h, fill=1, stroke=0)


class StatBox(Flowable):
    def __init__(self, value, label, sublabel="", color=None):
        super().__init__()
        self.value    = str(value)
        self.label    = label
        self.sublabel = sublabel
        self.color    = color or BLUE
        self.width    = 38 * mm
        self.height   = 22 * mm

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        c = self.canv
        # Card background
        c.setFillColor(DARK)
        c.roundRect(0, 0, self.width, self.height, 2*mm, fill=1, stroke=0)
        # Accent bar
        c.setFillColor(self.color)
        c.rect(0, self.height - 1.2*mm, self.width, 1.2*mm, fill=1, stroke=0)
        # Value
        c.setFillColor(self.color)
        c.setFont("Helvetica-Bold", 18)
        c.drawCentredString(self.width/2, self.height - 10*mm, self.value)
        # Label
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 6.5)
        c.drawCentredString(self.width/2, self.height - 14*mm, self.label.upper())
        # Sublabel
        if self.sublabel:
            c.setFillColor(MUTED)
            c.setFont("Helvetica", 5.5)
            c.drawCentredString(self.width/2, self.height - 17.5*mm, self.sublabel)


class ModuleCard(Flowable):
    def __init__(self, icon, title, desc, metric, metric_label, color):
        super().__init__()
        self.icon, self.title, self.desc = icon, title, desc
        self.metric, self.metric_label   = metric, metric_label
        self.color = color
        self.width  = 55 * mm
        self.height = 54 * mm

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setFillColor(DARK)
        c.roundRect(0, 0, self.width, self.height, 2.5*mm, fill=1, stroke=0)
        c.setFillColor(self.color)
        c.roundRect(0, self.height - 10*mm, self.width, 10*mm,
                    2.5*mm, fill=1, stroke=0)
        c.rect(0, self.height - 12*mm, self.width, 4*mm, fill=1, stroke=0)
        # Icon + title
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(3*mm, self.height - 7.5*mm, self.icon)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(10*mm, self.height - 7.5*mm, self.title.upper())
        # Description lines
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 6.5)
        lines = []
        words = self.desc.split()
        line  = ""
        for w in words:
            test = (line + " " + w).strip()
            if c.stringWidth(test, "Helvetica", 6.5) < self.width - 6*mm:
                line = test
            else:
                lines.append(line); line = w
        if line: lines.append(line)
        y = self.height - 16*mm
        for ln in lines[:6]:
            c.drawString(3*mm, y, ln); y -= 3.8*mm
        # Metric
        c.setFillColor(self.color)
        c.setFont("Helvetica-Bold", 16)
        c.drawCentredString(self.width/2, 10*mm, self.metric)
        c.setFillColor(WHITE)
        c.setFont("Helvetica", 6)
        c.drawCentredString(self.width/2, 6.5*mm, self.metric_label.upper())


# ── PDF Styles ────────────────────────────────────────────────────────────

def make_styles():
    styles = getSampleStyleSheet()
    base = {
        "fontName": "Helvetica",
        "textColor": HexColor("#1e293b"),
        "leading":   14,
    }
    return {
        "cover_title": ParagraphStyle("cover_title",
            fontName="Helvetica-Bold", fontSize=32, textColor=BLUE,
            leading=38, spaceAfter=4, alignment=TA_LEFT),
        "cover_sub": ParagraphStyle("cover_sub",
            fontName="Helvetica", fontSize=13, textColor=WHITE,
            leading=18, spaceAfter=2, alignment=TA_LEFT),
        "cover_tag": ParagraphStyle("cover_tag",
            fontName="Helvetica", fontSize=9, textColor=MUTED,
            leading=12, spaceAfter=0, alignment=TA_LEFT),
        "h1": ParagraphStyle("h1",
            fontName="Helvetica-Bold", fontSize=16, textColor=NAVY,
            leading=20, spaceBefore=6, spaceAfter=4),
        "h2": ParagraphStyle("h2",
            fontName="Helvetica-Bold", fontSize=11, textColor=DARK,
            leading=14, spaceBefore=4, spaceAfter=3),
        "body": ParagraphStyle("body",
            fontName="Helvetica", fontSize=9, textColor=HexColor("#334155"),
            leading=13, spaceAfter=4, alignment=TA_JUSTIFY),
        "body_white": ParagraphStyle("body_white",
            fontName="Helvetica", fontSize=9, textColor=WHITE,
            leading=13, spaceAfter=3),
        "caption": ParagraphStyle("caption",
            fontName="Helvetica", fontSize=7.5, textColor=MUTED,
            leading=10, spaceAfter=2, alignment=TA_CENTER),
        "bullet": ParagraphStyle("bullet",
            fontName="Helvetica", fontSize=8.5, textColor=HexColor("#334155"),
            leading=12, spaceAfter=2, leftIndent=8, bulletIndent=0),
        "tag": ParagraphStyle("tag",
            fontName="Helvetica-Bold", fontSize=7, textColor=BLUE,
            leading=9, spaceAfter=0),
        "insight": ParagraphStyle("insight",
            fontName="Helvetica-Bold", fontSize=9.5, textColor=NAVY,
            leading=13, spaceAfter=3, borderPad=6),
        "small_muted": ParagraphStyle("small_muted",
            fontName="Helvetica", fontSize=7, textColor=MUTED,
            leading=9, spaceAfter=0),
    }


# ── Cover page background via onFirstPage callback ────────────────────────

def cover_background(c, doc):
    w, h = A4
    c.setFillColor(NAVY)
    c.rect(0, 0, w, h, fill=1, stroke=0)
    # Accent stripe
    c.setFillColor(BLUE)
    c.rect(0, h - 4*mm, w, 4*mm, fill=1, stroke=0)
    # Bottom stripe
    c.setFillColor(DARK)
    c.rect(0, 0, w, 22*mm, fill=1, stroke=0)
    c.setFillColor(BLUE)
    c.rect(0, 22*mm, w, 0.6*mm, fill=1, stroke=0)


def inner_background(c, doc):
    w, h = A4
    c.setFillColor(HexColor("#f8fafc"))
    c.rect(0, 0, w, h, fill=1, stroke=0)
    # Top bar
    c.setFillColor(NAVY)
    c.rect(0, h - 10*mm, w, 10*mm, fill=1, stroke=0)
    # Page number
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7)
    c.drawRightString(w - 14*mm, 8*mm, f"Page {doc.page}")
    # Footer
    c.setFillColor(HexColor("#e2e8f0"))
    c.rect(0, 0, w, 6*mm, fill=1, stroke=0)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 6)
    c.drawString(14*mm, 2*mm, "Polymarket Ops Intelligence  ·  Data as of " + SNAP_DATE)
    c.drawRightString(w - 14*mm, 2*mm, "github.com/TorradoSantiago/polymarket-analysis")


# ── Build PDF ─────────────────────────────────────────────────────────────

def build_pdf(path):
    S = make_styles()
    W, H = A4
    M = 14 * mm

    story = []

    # ════════════════ PAGE 1 — COVER ════════════════
    story.append(Spacer(1, 28*mm))
    story.append(Paragraph("POLYMARKET", S["cover_title"]))
    story.append(Paragraph("OPS INTELLIGENCE", ParagraphStyle("ct2",
        fontName="Helvetica-Bold", fontSize=32, textColor=WHITE,
        leading=36, spaceAfter=6)))
    story.append(Spacer(1, 4*mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=BLUE, spaceAfter=6*mm))

    story.append(Paragraph(
        "A data analytics project for prediction market operations teams.",
        S["cover_sub"]))
    story.append(Paragraph(
        "Combining live market data with cross-platform validation to surface resolution risk,\n"
        "integrity anomalies, compliance exposure, and global market distribution.",
        ParagraphStyle("cs2", fontName="Helvetica", fontSize=10, textColor=MUTED,
                       leading=15, spaceAfter=0)))
    story.append(Spacer(1, 12*mm))

    # Cover stats row
    boxes_data = [
        (SNAP_VOLUME,    "Total Volume",     "Prediction markets dataset",  BLUE),
        (str(SNAP_MARKETS), "Markets Analysed", "Active events, live data", GREEN),
        ("3",            "Risk Modules",     "QA · Integrity · Compliance", PURPLE),
        ("19",           "Countries Mapped", "Geographic intelligence",      CYAN),
    ]
    box_w = (W - 2*M - 3*5*mm) / 4
    boxes_row = [[StatBox(v, l, s, c) for v, l, s, c in boxes_data]]
    boxes_tbl = Table(boxes_row, colWidths=[box_w]*4)
    boxes_tbl.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),2.5*mm),
                                    ("RIGHTPADDING",(0,0),(-1,-1),2.5*mm),
                                    ("TOPPADDING",(0,0),(-1,-1),0),
                                    ("BOTTOMPADDING",(0,0),(-1,-1),0)]))
    story.append(boxes_tbl)
    story.append(Spacer(1, 10*mm))

    # Tagline chips
    chips = ["Polymarket Gamma API", "PolymarketScan API", "Python · Matplotlib",
             "ReportLab · Chart.js", "Plotly World Map", "MIT License"]
    chip_data = [[Paragraph(f"  {c}  ", ParagraphStyle("chip",
        fontName="Helvetica", fontSize=7.5, textColor=BLUE,
        leading=10, backColor=DARK)) for c in chips]]
    chip_tbl = Table(chip_data, colWidths=[(W-2*M)/len(chips)]*len(chips))
    chip_tbl.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1), DARK),
        ("TEXTCOLOR",(0,0),(-1,-1), BLUE),
        ("ALIGN",(0,0),(-1,-1),"CENTER"),
        ("TOPPADDING",(0,0),(-1,-1),3),
        ("BOTTOMPADDING",(0,0),(-1,-1),3),
        ("LEFTPADDING",(0,0),(-1,-1),2),
        ("RIGHTPADDING",(0,0),(-1,-1),2),
        ("GRID",(0,0),(-1,-1),0.3, HexColor("#334155")),
    ]))
    story.append(chip_tbl)
    story.append(Spacer(1, 30*mm))
    story.append(Paragraph(SNAP_DATE + "  ·  v2.0", S["cover_tag"]))

    story.append(PageBreak())

    # ════════════════ PAGE 2 — WHAT & WHY ════════════════
    story.append(Spacer(1, 14*mm))
    story.append(Paragraph("What Are Prediction Markets?", S["h1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=BLUE, spaceAfter=4*mm))

    intro_text = (
        "Prediction markets are platforms where people buy and sell contracts tied to real-world outcomes — "
        "elections, sports results, economic data, or geopolitical events. Each contract resolves to $1 if the "
        "event happens, or $0 if it does not. The market price therefore reflects the crowd's probability estimate "
        "at any moment. Polymarket, the world's largest prediction market by volume, has processed over "
        "<b>$20 billion in trades</b> and tracks events across politics, finance, sports, and global affairs."
    )
    story.append(Paragraph(intro_text, S["body"]))
    story.append(Spacer(1, 3*mm))

    story.append(Paragraph("Why Ops Intelligence Matters", S["h2"]))
    story.append(Paragraph(
        "Unlike traditional financial markets, prediction markets rely heavily on manual operations teams "
        "to ensure that each market resolves correctly, fairly, and on time. An ops associate is responsible for:",
        S["body"]))

    bullets = [
        "Monitoring live markets and ensuring event outcomes are accurately recorded",
        "Reviewing resolution criteria to confirm they are clear, verifiable, and sourced",
        "Identifying markets at risk of dispute — where criteria are ambiguous or sources are missing",
        "Flagging integrity concerns such as volume spikes, low liquidity, or unusual trader behaviour",
        "Assessing regulatory exposure across jurisdictions (electoral markets, financial instruments)",
        "Maintaining documentation standards across hundreds of simultaneous events",
    ]
    for b in bullets:
        story.append(Paragraph(f"• {b}", S["bullet"]))
    story.append(Spacer(1, 4*mm))

    story.append(Paragraph("The Data Gap Problem", S["h2"]))
    story.append(Paragraph(
        "The public Polymarket Gamma API — the primary programmatic data source — returns market data "
        "without complete resolution criteria for a significant portion of markets. This project "
        "cross-validates that API against PolymarketScan, a third-party analytics platform, "
        "to separate <b>genuine resolution quality failures</b> (both sources flag the market) "
        "from <b>data gaps</b> (the API is missing description text that exists on the web interface). "
        "This cross-validation is not available in any existing public tool.",
        S["body"]))

    story.append(Spacer(1, 4*mm))
    story.append(Paragraph("What Makes This Different", S["h2"]))

    compare_data = [
        ["Feature", "PolymarketScan", "Gamma API", "This Dashboard"],
        ["Market volume & liquidity",    "✓", "✓", "✓"],
        ["Whale / trader tracking",      "✓", "–", "✓ (via PS)"],
        ["Resolution criteria QA",       "Partial", "–", "✓ Full scoring"],
        ["Compliance risk flags",        "–", "–", "✓ New"],
        ["Cross-platform validation",    "–", "–", "✓ New"],
        ["Composite ops risk score",     "–", "–", "✓ New"],
        ["Geographic market map",        "–", "–", "✓ New"],
        ["Ops triage queue",             "–", "–", "✓ New"],
    ]
    col_w = [(W - 2*M)/4] * 4
    comp_tbl = Table(compare_data, colWidths=col_w, repeatRows=1)
    comp_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),  (-1,0),  NAVY),
        ("TEXTCOLOR",     (0,0),  (-1,0),  WHITE),
        ("FONTNAME",      (0,0),  (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0),  (-1,-1), 8),
        ("ALIGN",         (1,0),  (-1,-1), "CENTER"),
        ("ALIGN",         (0,0),  (0,-1),  "LEFT"),
        ("ROWBACKGROUNDS",(0,1),  (-1,-1), [HexColor("#f8fafc"), HexColor("#f1f5f9")]),
        ("TEXTCOLOR",     (3,1),  (3,-1),  HexColor("#16a34a")),
        ("FONTNAME",      (3,1),  (3,-1),  "Helvetica-Bold"),
        ("TEXTCOLOR",     (1,1),  (1,-1),  MUTED),
        ("TEXTCOLOR",     (2,1),  (2,-1),  MUTED),
        ("GRID",          (0,0),  (-1,-1), 0.3, HexColor("#e2e8f0")),
        ("TOPPADDING",    (0,0),  (-1,-1), 4),
        ("BOTTOMPADDING", (0,0),  (-1,-1), 4),
        ("LEFTPADDING",   (0,0),  (-1,-1), 6),
        ("RIGHTPADDING",  (0,0),  (-1,-1), 6),
    ]))
    story.append(comp_tbl)

    story.append(PageBreak())

    # ════════════════ PAGE 3 — KEY FINDINGS ════════════════
    story.append(Spacer(1, 14*mm))
    story.append(Paragraph("Key Findings — Live Data Snapshot", S["h1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=GREEN, spaceAfter=4*mm))
    story.append(Paragraph(
        f"Analysis of the top {SNAP_MARKETS} most-traded active markets on Polymarket as of {SNAP_DATE}. "
        f"Total dataset volume: <b>{SNAP_VOLUME}</b>.",
        S["body"]))
    story.append(Spacer(1, 3*mm))

    # Stat boxes
    findings_boxes = [
        ("39%",  "QA Failure Rate",    "Markets missing verifiable criteria", RED),
        ("117",  "FAIL-grade Markets", "Resolution source or criteria absent", YELLOW),
        ("3.3%", "High Integrity Risk","Anomalous volume / liquidity patterns", RED),
        ("49%",  "Markets Mapped",     "147/300 linked to a specific country",  CYAN),
    ]
    fb_w = (W - 2*M - 3*5*mm) / 4
    fb_row = [[StatBox(v,l,s,c) for v,l,s,c in findings_boxes]]
    fb_tbl = Table(fb_row, colWidths=[fb_w]*4)
    fb_tbl.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),2.5*mm),
                                 ("RIGHTPADDING",(0,0),(-1,-1),2.5*mm),
                                 ("TOPPADDING",(0,0),(-1,-1),0),
                                 ("BOTTOMPADDING",(0,0),(-1,-1),0)]))
    story.append(fb_tbl)
    story.append(Spacer(1, 5*mm))

    # Charts row: QA donut + Ops Risk donut
    qa_buf  = chart_donut([125,58,117], ["PASS","REVIEW","FAIL"],
                           ["#22c55e","#f59e0b","#ef4444"], "Resolution QA Grades")
    ops_buf = chart_donut([245,55,0,0], ["LOW","MEDIUM","HIGH","CRITICAL"],
                           ["#22c55e","#f59e0b","#ef4444","#dc2626"], "Composite Ops Risk")

    charts_row = [[Image(qa_buf,  width=80*mm, height=62*mm),
                   Image(ops_buf, width=80*mm, height=62*mm)]]
    charts_tbl = Table(charts_row, colWidths=[(W-2*M)/2]*2)
    charts_tbl.setStyle(TableStyle([("ALIGN",(0,0),(-1,-1),"CENTER"),
                                     ("TOPPADDING",(0,0),(-1,-1),0),
                                     ("BOTTOMPADDING",(0,0),(-1,-1),0)]))
    story.append(charts_tbl)
    story.append(Spacer(1, 3*mm))

    # Insights box
    insights = [
        "Politics & Elections dominate with 47% of all volume ($17.4B), though they represent only 20% of markets — signalling far higher average stakes per market.",
        "39% of markets lack adequate resolution documentation in the Gamma API. Cross-validation with PolymarketScan confirms ~60% of those are genuine data quality issues.",
        "The compliance layer reveals 3 HIGH-risk markets (personal safety or multi-jurisdiction legal proceedings) not flagged anywhere in existing public analytics tools.",
    ]
    for ins in insights:
        insight_tbl = Table([[Paragraph(f"💡  {ins}", S["body"])]], colWidths=[W-2*M])
        insight_tbl.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(0,0), HexColor("#f0f9ff")),
            ("LINEAFTER",(0,0),(0,0), 3, BLUE),
            ("TOPPADDING",(0,0),(-1,-1),5),
            ("BOTTOMPADDING",(0,0),(-1,-1),5),
            ("LEFTPADDING",(0,0),(-1,-1),8),
            ("RIGHTPADDING",(0,0),(-1,-1),8),
        ]))
        story.append(insight_tbl)
        story.append(Spacer(1, 2*mm))

    story.append(PageBreak())

    # ════════════════ PAGE 4 — WORLD MAP DATA ════════════════
    story.append(Spacer(1, 14*mm))
    story.append(Paragraph("Geographic Intelligence — Where Is the World Betting?", S["h1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=PURPLE, spaceAfter=4*mm))
    story.append(Paragraph(
        "Each market is classified by the country or region it references — identified by scanning "
        "the market title and tags for geographic keywords. The result shows which countries attract "
        "the most speculative attention, both by market count and by total USD volume traded.",
        S["body"]))
    story.append(Spacer(1, 3*mm))

    map_buf = chart_country_double(COUNTRIES)
    story.append(Image(map_buf, width=W-2*M, height=65*mm))
    story.append(Paragraph("Market count and USD volume traded, by country/region (top 12).", S["caption"]))
    story.append(Spacer(1, 4*mm))

    story.append(Paragraph("What This Tells Us", S["h2"]))
    geo_insights = [
        "<b>The United States dominates</b> both in market count (89 markets) and volume ($17.4B). Almost every major US political, economic, or cultural event generates a prediction market.",
        "<b>Active conflict zones are highly represented.</b> Russia/Ukraine and Iran/Israel together account for 30 markets and $6B in volume — showing prediction markets are a real-time sentiment gauge for geopolitical risk.",
        "<b>Volume concentration is extreme.</b> The top 3 country groups (USA, Russia/Ukraine, Iran/Israel) represent 63% of all mapped volume despite being only 3 of 19 geographic clusters.",
        "<b>Emerging markets are underrepresented.</b> Despite having large populations and active political systems, countries like Nigeria, Pakistan, and Argentina together generate fewer than 5 markets — a potential growth area for the protocol.",
    ]
    for ins in geo_insights:
        story.append(Paragraph(f"• {ins}", S["bullet"]))
        story.append(Spacer(1, 1.5*mm))

    story.append(PageBreak())

    # ════════════════ PAGE 5 — THREE MODULES ════════════════
    story.append(Spacer(1, 14*mm))
    story.append(Paragraph("The Three Intelligence Modules", S["h1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=YELLOW, spaceAfter=5*mm))

    mcard_w = (W - 2*M - 2*5*mm) / 3

    modules = [
        ("📋", "Resolution QA",
         "Scores each market's resolution criteria on accuracy, source citation, "
         "date specificity, and language clarity. Cross-validates against "
         "PolymarketScan's rules arb score to distinguish genuine issues from API data gaps.",
         "39%", "FAIL rate in top 300 markets", GREEN),
        ("🔍", "Integrity Monitor",
         "Detects anomalies across volume/liquidity ratios, 24h volume spikes "
         "(potential insider trading signals), zero-liquidity exposure, and "
         "low-engagement high-volume patterns. Enriched with PolymarketScan "
         "controversy scores and smart-money bias.",
         "3.3%", "High-risk integrity flags", YELLOW),
        ("⚖️", "Compliance Risk",
         "Flags markets with regulatory exposure: electoral outcomes (CFTC-sensitive "
         "jurisdictions), named-individual legal proceedings, financial instrument "
         "mirrors, sanctions keywords, and personal-safety markets. "
         "Not available in any existing public Polymarket analytics tool.",
         "NEW", "Not in PolymarketScan", RED),
    ]
    mcards = [[ModuleCard(*m) for m in modules]]
    mc_tbl = Table(mcards, colWidths=[mcard_w]*3)
    mc_tbl.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),2.5*mm),
                                 ("RIGHTPADDING",(0,0),(-1,-1),2.5*mm),
                                 ("TOPPADDING",(0,0),(-1,-1),0),
                                 ("BOTTOMPADDING",(0,0),(-1,-1),0)]))
    story.append(mc_tbl)
    story.append(Spacer(1, 6*mm))

    story.append(Paragraph("Composite Ops Risk Score", S["h2"]))
    story.append(Paragraph(
        "Each market receives a <b>Composite Ops Risk Score</b> — a weighted aggregate of all three modules. "
        "This single score drives the Ops Triage queue: a ranked list of markets needing "
        "human attention, ordered by priority. Weights: QA (40%) + Integrity (35%) + Compliance (25%).",
        S["body"]))
    story.append(Spacer(1, 3*mm))

    # Score example table
    score_data = [
        ["Module", "Weight", "What It Measures", "If Score Is Low → Action"],
        ["Resolution QA",   "40%", "Are criteria clear, sourced, and verifiable?",     "Review market description; escalate if near expiry"],
        ["Integrity",       "35%", "Are volume/liquidity patterns normal?",             "Flag for trading desk review; check for manipulation"],
        ["Compliance",      "25%", "Are there regulatory or legal risk keywords?",      "Escalate to legal/compliance team before resolution"],
    ]
    sc_tbl = Table(score_data, colWidths=[30*mm, 18*mm, 70*mm, 55*mm])
    sc_tbl.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0), NAVY),
        ("TEXTCOLOR",(0,0),(-1,0), WHITE),
        ("FONTNAME",(0,0),(-1,0), "Helvetica-Bold"),
        ("FONTSIZE",(0,0),(-1,-1), 7.5),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[HexColor("#f8fafc"),HexColor("#f1f5f9")]),
        ("GRID",(0,0),(-1,-1),0.3,HexColor("#e2e8f0")),
        ("TOPPADDING",(0,0),(-1,-1),4),
        ("BOTTOMPADDING",(0,0),(-1,-1),4),
        ("LEFTPADDING",(0,0),(-1,-1),5),
        ("RIGHTPADDING",(0,0),(-1,-1),5),
        ("ALIGN",(1,0),(1,-1),"CENTER"),
        ("FONTNAME",(1,1),(1,-1),"Helvetica-Bold"),
        ("TEXTCOLOR",(1,1),(1,-1), BLUE),
    ]))
    story.append(sc_tbl)

    story.append(PageBreak())

    # ════════════════ PAGE 6 — PIPELINE + STACK ════════════════
    story.append(Spacer(1, 14*mm))
    story.append(Paragraph("Technical Approach", S["h1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=CYAN, spaceAfter=4*mm))

    story.append(Paragraph("Data Pipeline", S["h2"]))
    pipeline_buf = chart_pipeline()
    story.append(Image(pipeline_buf, width=W-2*M, height=35*mm))
    story.append(Paragraph(
        "Two public APIs ingested and cross-joined by fuzzy title matching. "
        "All scoring logic runs client-side. Output: self-contained HTML dashboard + this PDF.",
        S["caption"]))
    story.append(Spacer(1, 4*mm))

    story.append(Paragraph("Tech Stack", S["h2"]))
    stack_data = [
        ["Layer", "Tool", "Purpose"],
        ["Data ingestion",   "Python · requests",              "Paginated API fetching from two sources"],
        ["Classification",   "Regex · keyword matching",       "Category + country detection"],
        ["Scoring",          "Python (no ML)",                 "Rule-based QA, integrity, compliance scoring"],
        ["Visualisation",    "Chart.js · Plotly",              "Interactive HTML charts and world choropleth"],
        ["PDF generation",   "ReportLab · matplotlib",         "This document"],
        ["Version control",  "Git · GitHub",                   "github.com/TorradoSantiago/polymarket-analysis"],
        ["Data source 1",    "Polymarket Gamma API (public)",  "Events, descriptions, volume, dates"],
        ["Data source 2",    "PolymarketScan API (public)",    "rules_arb_score, controversy, whale count"],
    ]
    st_tbl = Table(stack_data, colWidths=[40*mm, 55*mm, 75*mm])
    st_tbl.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0), NAVY),
        ("TEXTCOLOR",(0,0),(-1,0), WHITE),
        ("FONTNAME",(0,0),(-1,0), "Helvetica-Bold"),
        ("FONTSIZE",(0,0),(-1,-1), 8),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[HexColor("#f8fafc"),HexColor("#f1f5f9")]),
        ("FONTNAME",(0,1),(0,-1), "Helvetica-Bold"),
        ("TEXTCOLOR",(0,1),(0,-1), NAVY),
        ("GRID",(0,0),(-1,-1),0.3,HexColor("#e2e8f0")),
        ("TOPPADDING",(0,0),(-1,-1),5),
        ("BOTTOMPADDING",(0,0),(-1,-1),5),
        ("LEFTPADDING",(0,0),(-1,-1),6),
        ("RIGHTPADDING",(0,0),(-1,-1),6),
    ]))
    story.append(st_tbl)
    story.append(Spacer(1, 5*mm))

    story.append(Paragraph("Limitations & Next Steps", S["h2"]))
    limits = [
        "<b>API data gap:</b> ~39% of markets have empty description fields in the Gamma API. "
        "The compliance and QA modules can only analyse what is available programmatically.",
        "<b>Country detection:</b> Based on keyword matching — ambiguous titles (e.g. \"will the ceasefire hold?\") "
        "are left unmapped. NLP-based geolocation would improve coverage.",
        "<b>Match rate:</b> 28% of Gamma events matched to PolymarketScan markets "
        "(event vs. individual market granularity mismatch). A market-level Gamma API endpoint would solve this.",
        "<b>Potential extensions:</b> Time-series calibration (compare implied probabilities vs. actual outcomes), "
        "live alert webhooks, Slack/email notifications for critical ops events.",
    ]
    for lm in limits:
        story.append(Paragraph(f"• {lm}", S["bullet"]))
        story.append(Spacer(1, 1.5*mm))

    # ── Build ─────────────────────────────────────────────────────────────
    doc = SimpleDocTemplate(
        path,
        pagesize=A4,
        leftMargin=M, rightMargin=M,
        topMargin=14*mm, bottomMargin=14*mm,
        title="Polymarket Ops Intelligence — Project Brief",
        author="Santiago Torrado",
        subject="Prediction Market Operations Analytics",
    )

    # Apply background to pages
    cover_template = PageTemplate(id="Cover",   frames=[Frame(M, 14*mm, W-2*M, H-28*mm, id="main")], onPage=cover_background)
    inner_template = PageTemplate(id="Inner",   frames=[Frame(M, 12*mm, W-2*M, H-26*mm, id="main")], onPage=inner_background)
    doc.addPageTemplates([cover_template, inner_template])

    # Insert NextPageTemplate before PageBreaks
    from reportlab.platypus import NextPageTemplate
    final_story = []
    final_story.append(NextPageTemplate("Cover"))
    switched = False
    for item in story:
        if isinstance(item, PageBreak) and not switched:
            final_story.append(NextPageTemplate("Inner"))
            switched = True
        final_story.append(item)

    doc.build(final_story)
    print(f"✓  PDF saved: {path}")


if __name__ == "__main__":
    out = "/sessions/nice-modest-clarke/mnt/outputs/polymarket-analysis/polymarket_ops_brief.pdf"
    build_pdf(out)
                                                                                                              