from __future__ import annotations

import io
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime
from functools import partial
from typing import List

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table

W, H = A4

INK = colors.HexColor("#0F1420")
WHITE = colors.white
BLUE = colors.HexColor("#0A84FF")
BLUE_LIGHT = colors.HexColor("#EBF4FF")
BLUE_MID = colors.HexColor("#C8E0FF")
AMBER = colors.HexColor("#F5A623")
AMBER_LT = colors.HexColor("#FFF8EC")
RED = colors.HexColor("#FF3B5C")
RED_LT = colors.HexColor("#FFF0F3")
GREEN = colors.HexColor("#00A86B")
GREEN_LT = colors.HexColor("#EDFAF4")
GREY_DARK = colors.HexColor("#2C3E50")
GREY_MID = colors.HexColor("#64748B")
GREY_LT = colors.HexColor("#F1F5F9")
GREY_LINE = colors.HexColor("#E2E8F0")
ORANGE = colors.HexColor("#FF6B35")
ORANGE_LT = colors.HexColor("#FFF4EF")


class MilestoneItem(BaseModel):
    phase: str
    planStart: str = ""
    planEnd: str = ""
    actualEnd: str = ""
    predictedEnd: str = ""
    varianceDays: int = 0
    status: str = ""


class MilestoneForecastItem(BaseModel):
    phase: str
    status: str = ""
    confidence: int = 0
    reasoning: str = ""


class RiskItem(BaseModel):
    number: str
    severity: str = ""
    title: str = ""
    impact: str = ""
    owner: str = ""
    action: str = ""


class ReportRequest(BaseModel):
    projectName: str
    clientName: str
    modules: str
    currentPhase: str
    health: str
    originalGoLive: str
    predictedGoLive: str
    varianceDays: int
    confidence: int
    uatCompletion: int
    generatedDate: str
    executiveSummary: str
    milestones: List[MilestoneItem] = Field(default_factory=list)
    milestoneForecasts: List[MilestoneForecastItem] = Field(default_factory=list)
    risks: List[RiskItem] = Field(default_factory=list)
    actionsNow: List[str] = Field(default_factory=list)
    actionsMonth: List[str] = Field(default_factory=list)
    varianceAnalysisText: str
    recoveryPath: str


class SupportTopAgingTicket(BaseModel):
    id: str = ""
    title: str = ""
    ageDays: int = 0
    client: str = ""


class SupportMonthlyTrendItem(BaseModel):
    month: str
    created: int = 0
    resolved: int = 0


class SupportModuleBreakdownItem(BaseModel):
    module: str
    open: int = 0
    critical: int = 0


class SupportReportRequest(BaseModel):
    reportDate: str
    periodStart: str
    periodEnd: str
    clientFilter: str
    totalTickets: int = 0
    openIncidents: int = 0
    closedIncidents: int = 0
    pendingCustomer: int = 0
    pendingInternal: int = 0
    openCRs: int = 0
    closedCRs: int = 0
    slaCompliance: float = 0
    slaViolated: int = 0
    avgResolutionHrs: float = 0
    csatAvg: float = 0
    criticalOpen: int = 0
    highOpen: int = 0
    breachedTickets: int = 0
    moduleHotspot: str = ""
    topAgingTicket: SupportTopAgingTicket = Field(default_factory=SupportTopAgingTicket)
    tickets: List[dict] = Field(default_factory=list)
    clients: List[dict] = Field(default_factory=list)
    consultants: List[dict] = Field(default_factory=list)
    monthlyTrend: List[SupportMonthlyTrendItem] = Field(default_factory=list)
    moduleBreakdown: List[SupportModuleBreakdownItem] = Field(default_factory=list)


def S(name, **kw):
    base = dict(fontName="Helvetica", fontSize=10, textColor=GREY_DARK, leading=14, spaceAfter=0, spaceBefore=0)
    base.update(kw)
    return ParagraphStyle(name, **base)


sTitle = S("title", fontName="Helvetica-Bold", fontSize=22, textColor=WHITE, leading=28)
sSubtitle = S("sub", fontName="Helvetica", fontSize=10, textColor=colors.HexColor("#B0C4DE"), leading=14)
sSection = S("sec", fontName="Helvetica-Bold", fontSize=11, textColor=BLUE, leading=16, spaceBefore=6)
sSectionSm = S("secsm", fontName="Helvetica-Bold", fontSize=9, textColor=GREY_MID, leading=12, spaceAfter=2)
sBody = S("body", fontName="Helvetica", fontSize=9, textColor=GREY_DARK, leading=14)
sBodySm = S("bodysm", fontName="Helvetica", fontSize=8, textColor=GREY_MID, leading=12)
sBold = S("bold", fontName="Helvetica-Bold", fontSize=9, textColor=GREY_DARK, leading=14)


def HR(color=GREY_LINE, thickness=0.5, spB=4, spA=4):
    return HRFlowable(width="100%", thickness=thickness, color=color, spaceAfter=spA, spaceBefore=spB)


def sp(n=4):
    return Spacer(1, n)


def status_color(s):
    return {
        "Complete": (GREEN, GREEN_LT, " Complete"),
        "At Risk": (AMBER, AMBER_LT, " At Risk"),
        "Delayed": (RED, RED_LT, " Delayed"),
    }.get(s, (GREY_MID, GREY_LT, s))


def on_page(canvas, doc, project_name, generated_date):
    canvas.saveState()
    pw = doc.pagesize[0]
    ph = doc.pagesize[1]

    if doc.page == 1:
        canvas.setFillColor(colors.HexColor("#07090F"))
        canvas.rect(0, ph - 48 * mm, pw, 48 * mm, fill=1, stroke=0)
        canvas.setFillColor(BLUE)
        canvas.rect(0, ph - 48 * mm, pw, 1.2 * mm, fill=1, stroke=0)
        canvas.setFillColor(BLUE)
        canvas.rect(0, 0, 3, ph, fill=1, stroke=0)
        canvas.setFillColor(BLUE)
        canvas.roundRect(15 * mm, ph - 18 * mm, 10 * mm, 10 * mm, 2, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", 12)
        canvas.setFillColor(WHITE)
        canvas.drawCentredString(20 * mm, ph - 14 * mm, "F")
        canvas.setFont("Helvetica-Bold", 16)
        canvas.setFillColor(WHITE)
        canvas.drawString(28 * mm, ph - 13.5 * mm, "Fayol")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#7090B0"))
        canvas.drawString(28 * mm, ph - 18.5 * mm, "SAP Project Automation")
        canvas.setFont("Helvetica-Bold", 18)
        canvas.setFillColor(WHITE)
        canvas.drawString(15 * mm, ph - 32 * mm, "PROJECT INTELLIGENCE REPORT")
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(colors.HexColor("#7090B0"))
        canvas.drawString(15 * mm, ph - 38 * mm, "Confidential  —  For Internal & Steering Committee Use")
        canvas.setFont("Helvetica-Bold", 11)
        canvas.setFillColor(colors.HexColor("#A8C4E0"))
        canvas.drawRightString(pw - 15 * mm, ph - 32 * mm, project_name)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#7090B0"))
        canvas.drawRightString(pw - 15 * mm, ph - 38 * mm, generated_date)
    else:
        canvas.setFillColor(colors.HexColor("#07090F"))
        canvas.rect(0, ph - 12 * mm, pw, 12 * mm, fill=1, stroke=0)
        canvas.setFillColor(BLUE)
        canvas.rect(0, ph - 12 * mm, pw, 1 * mm, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(WHITE)
        canvas.drawString(15 * mm, ph - 8 * mm, "Fayol  Project Intelligence Report")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#7090B0"))
        canvas.drawRightString(pw - 15 * mm, ph - 8 * mm, project_name)
        canvas.setFillColor(BLUE)
        canvas.rect(0, 0, 3, ph, fill=1, stroke=0)

    canvas.setFillColor(GREY_LINE)
    canvas.rect(0, 0, pw, 10 * mm, fill=1, stroke=0)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(GREY_MID)
    canvas.drawString(15 * mm, 3.5 * mm, "Fayol  SAP Project Automation   |   Confidential")
    canvas.drawRightString(pw - 15 * mm, 3.5 * mm, f"Page {doc.page}")
    canvas.restoreState()


def on_support_page(canvas, doc, project_name, generated_date):
    canvas.saveState()
    pw = doc.pagesize[0]
    ph = doc.pagesize[1]

    if doc.page == 1:
        canvas.setFillColor(colors.HexColor("#07090F"))
        canvas.rect(0, ph - 48 * mm, pw, 48 * mm, fill=1, stroke=0)
        canvas.setFillColor(BLUE)
        canvas.rect(0, ph - 48 * mm, pw, 1.2 * mm, fill=1, stroke=0)
        canvas.setFillColor(BLUE)
        canvas.rect(0, 0, 3, ph, fill=1, stroke=0)
        canvas.setFillColor(BLUE)
        canvas.roundRect(15 * mm, ph - 18 * mm, 10 * mm, 10 * mm, 2, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", 12)
        canvas.setFillColor(WHITE)
        canvas.drawCentredString(20 * mm, ph - 14 * mm, "F")
        canvas.setFont("Helvetica-Bold", 16)
        canvas.setFillColor(WHITE)
        canvas.drawString(28 * mm, ph - 13.5 * mm, "Fayol")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#7090B0"))
        canvas.drawString(28 * mm, ph - 18.5 * mm, "SAP Project Automation")
        canvas.setFont("Helvetica-Bold", 18)
        canvas.setFillColor(WHITE)
        canvas.drawString(15 * mm, ph - 32 * mm, "AMS SUPPORT INTELLIGENCE REPORT")
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(colors.HexColor("#7090B0"))
        canvas.drawString(15 * mm, ph - 38 * mm, "Confidential  -  For Internal & Steering Committee Use")
        canvas.setFont("Helvetica-Bold", 11)
        canvas.setFillColor(colors.HexColor("#A8C4E0"))
        canvas.drawRightString(pw - 15 * mm, ph - 32 * mm, project_name)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#7090B0"))
        canvas.drawRightString(pw - 15 * mm, ph - 38 * mm, generated_date)
    else:
        canvas.setFillColor(colors.HexColor("#07090F"))
        canvas.rect(0, ph - 12 * mm, pw, 12 * mm, fill=1, stroke=0)
        canvas.setFillColor(BLUE)
        canvas.rect(0, ph - 12 * mm, pw, 1 * mm, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(WHITE)
        canvas.drawString(15 * mm, ph - 8 * mm, "Fayol  AMS Support Intelligence Report")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#7090B0"))
        canvas.drawRightString(pw - 15 * mm, ph - 8 * mm, project_name)
        canvas.setFillColor(BLUE)
        canvas.rect(0, 0, 3, ph, fill=1, stroke=0)

    canvas.setFillColor(GREY_LINE)
    canvas.rect(0, 0, pw, 10 * mm, fill=1, stroke=0)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(GREY_MID)
    canvas.drawString(15 * mm, 3.5 * mm, "Fayol  SAP Project Automation   |   Confidential")
    canvas.drawRightString(pw - 15 * mm, 3.5 * mm, f"Page {doc.page}")
    canvas.restoreState()


def make_variance_chart(milestones, width_mm, height_mm):
    fig, ax = plt.subplots(figsize=(width_mm / 25.4, height_mm / 25.4), facecolor="#F1F5F9")
    ax.set_facecolor("#F1F5F9")

    phases = [m["phase"] for m in milestones]
    variance = [m["varianceDays"] for m in milestones]
    complete = [m["status"] == "Complete" for m in milestones]

    from datetime import datetime

    def days_between(s, e):
        for pattern in ("%d %b %y", "%d %b %Y", "%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
            try:
                return max(1, (datetime.strptime(e, pattern) - datetime.strptime(s, pattern)).days)
            except Exception:
                continue
        return 10

    planned = []
    for milestone in milestones:
        try:
            planned.append(days_between(milestone["planStart"], milestone["planEnd"]))
        except Exception:
            planned.append(10)

    y = np.arange(len(phases))
    bar_h = 0.45
    max_val = max(max(planned), max(variance)) if variance else 10

    for i, (p, v, done) in enumerate(zip(planned, variance, complete)):
        ax.barh(y[i] + bar_h / 2, p, bar_h, color="#C8E0FF", edgecolor="none", zorder=2)
        vc = "#00A86B" if done else ("#FF3B5C" if v > 20 else "#F5A623")
        ax.barh(y[i] - bar_h / 2, v, bar_h, color=vc, edgecolor="none", zorder=2, alpha=0.9)
        ax.text(p + 0.5, y[i] + bar_h / 2, f"{p}d", va="center", ha="left", fontsize=6.5, color="#64748B")
        ax.text(v + 0.5, y[i] - bar_h / 2, f"+{v}d", va="center", ha="left", fontsize=6.5, color=vc, fontweight="bold")

    ax.set_yticks(y)
    ax.set_yticklabels(phases, fontsize=7.5, color="#2C3E50")
    ax.set_xlabel("Days", fontsize=7, color="#64748B")
    ax.tick_params(axis="x", labelsize=7, colors="#64748B")
    ax.tick_params(axis="y", length=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color("#E2E8F0")
    ax.set_xlim(0, max_val * 1.2)
    ax.xaxis.grid(True, color="#E2E8F0", linestyle="--", linewidth=0.5, zorder=1)
    ax.set_axisbelow(True)
    p1 = mpatches.Patch(color="#C8E0FF", label="Planned Duration")
    p2 = mpatches.Patch(color="#00A86B", label="Variance  Completed")
    p3 = mpatches.Patch(color="#FF3B5C", label="Variance  Delayed (High)")
    p4 = mpatches.Patch(color="#F5A623", label="Variance  Delayed (Mod)")
    ax.legend(handles=[p1, p2, p3, p4], fontsize=6.5, loc="lower right", framealpha=0.8, edgecolor="#E2E8F0")
    ax.set_title("Schedule Variance by Phase  Planned Duration vs Delay (days)", fontsize=8, color="#2C3E50", pad=8, fontweight="bold")
    plt.tight_layout(pad=0.8)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=180, bbox_inches="tight", facecolor="#F1F5F9")
    plt.close(fig)
    buf.seek(0)
    return buf


def make_variance_analysis_chart(milestones, width_mm, height_mm):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(width_mm / 25.4, height_mm / 25.4), facecolor="#F1F5F9")
    fig.patch.set_facecolor("#F1F5F9")

    variances = [m["varianceDays"] for m in milestones]
    complete = [m["status"] == "Complete" for m in milestones]
    internal_v = 0
    external_v = sum(variances)
    donut_sizes = [external_v, internal_v] if external_v > 0 else [1, 0]
    donut_labels = [f"External Delays\n(+{external_v}d)", f"Internal\nDelays ({internal_v}d)"]
    donut_colours = ["#FF3B5C", "#00A86B"]
    explode = (0.04, 0)

    ax1.set_facecolor("#F1F5F9")
    wedges, texts, autotexts = ax1.pie(
        donut_sizes,
        labels=None,
        colors=donut_colours,
        explode=explode,
        autopct=lambda p: f"{p:.0f}%" if p > 5 else "",
        startangle=90,
        wedgeprops=dict(width=0.55, edgecolor="white", linewidth=2),
        pctdistance=0.75,
    )
    for at in autotexts:
        at.set_fontsize(8)
        at.set_fontweight("bold")
        at.set_color("white")
    total_delay = sum(variances)
    ax1.text(0, 0.08, f"{total_delay}d", ha="center", va="center", fontsize=16, fontweight="bold", color="#2C3E50")
    ax1.text(0, -0.18, "Total\nDelay", ha="center", va="center", fontsize=7, color="#64748B")
    legend_elements = [mpatches.Patch(color=c, label=l) for c, l in zip(donut_colours, donut_labels)]
    ax1.legend(handles=legend_elements, loc="lower center", fontsize=6.5, bbox_to_anchor=(0.5, -0.18), ncol=1, framealpha=0.8, edgecolor="#E2E8F0", handlelength=1.2)
    ax1.set_title("Delay Attribution by Cause", fontsize=8, fontweight="bold", color="#2C3E50", pad=10)

    ax2.set_facecolor("#F1F5F9")
    phases_short = [m["phase"][:10] for m in milestones]
    cum_total = []
    running = 0
    for v in variances:
        running += v
        cum_total.append(running)
    x = range(len(phases_short))

    ax2.fill_between(x, cum_total, alpha=0.12, color="#FF3B5C")
    ax2.plot(x, cum_total, color="#FF3B5C", linewidth=2.5, marker="o", markersize=5, markerfacecolor="white", markeredgecolor="#FF3B5C", markeredgewidth=2, zorder=5)
    ax2.axhline(0, color="#00A86B", linewidth=1.2, linestyle="--", alpha=0.7)

    peak_idx = cum_total.index(max(cum_total))
    ax2.annotate(f"+{cum_total[peak_idx]}d", xy=(peak_idx, cum_total[peak_idx]), xytext=(peak_idx + 0.1, cum_total[peak_idx] + max(cum_total) * 0.05), fontsize=7, color="#FF3B5C", fontweight="bold")

    complete_x = [i for i, milestone in enumerate(milestones) if milestone["status"] == "Complete"]
    delayed_x = [i for i, milestone in enumerate(milestones) if milestone["status"] != "Complete"]
    if complete_x:
        ax2.scatter(complete_x, [cum_total[i] for i in complete_x], color="#00A86B", s=40, zorder=6)
    if delayed_x:
        ax2.scatter(delayed_x, [cum_total[i] for i in delayed_x], color="#FF3B5C", s=40, zorder=6)

    ax2.set_xticks(list(x))
    ax2.set_xticklabels(phases_short, fontsize=6.5, rotation=25, ha="right", color="#2C3E50")
    ax2.set_ylabel("Cumulative Delay (days)", fontsize=7, color="#64748B")
    ax2.tick_params(axis="y", labelsize=7, colors="#64748B")
    ax2.tick_params(axis="x", length=0)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    ax2.spines["left"].set_color("#E2E8F0")
    ax2.spines["bottom"].set_color("#E2E8F0")
    ax2.yaxis.grid(True, color="#E2E8F0", linestyle="--", linewidth=0.5)
    ax2.set_axisbelow(True)
    p_done = mpatches.Patch(color="#00A86B", label="Completed Phases")
    p_del = mpatches.Patch(color="#FF3B5C", label="Delayed / At Risk")
    ax2.legend(handles=[p_done, p_del], fontsize=6.5, loc="upper left", framealpha=0.8, edgecolor="#E2E8F0")
    ax2.set_title("Cumulative Delay Build-up Across Phases", fontsize=8, fontweight="bold", color="#2C3E50", pad=10)

    plt.tight_layout(pad=1.0)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=180, bbox_inches="tight", facecolor="#F1F5F9")
    plt.close(fig)
    buf.seek(0)
    return buf


def generate_pdf(data: dict) -> bytes:
    buf = io.BytesIO()
    project_name = data.get("projectName", "Project")
    modules = data.get("modules", "")
    current_phase = data.get("currentPhase", "")
    health = data.get("health", "Amber")
    original_gl = data.get("originalGoLive", "")
    predicted_gl = data.get("predictedGoLive", "")
    variance_days = data.get("varianceDays", 0)
    confidence = data.get("confidence", 0)
    uat_pct = data.get("uatCompletion", 0)
    gen_date = data.get("generatedDate", "")
    exec_summary = data.get("executiveSummary", "")
    milestones = data.get("milestones", [])
    forecasts = data.get("milestoneForecasts", [])
    risks = data.get("risks", [])
    actions_now = data.get("actionsNow", [])
    actions_month = data.get("actionsMonth", [])
    va_text_raw = data.get("varianceAnalysisText", "")
    recovery_path = data.get("recoveryPath", "")

    health_color = {"Green": GREEN, "Amber": AMBER, "Red": RED}.get(health, AMBER)
    health_bg = {"Green": GREEN_LT, "Amber": AMBER_LT, "Red": RED_LT}.get(health, AMBER_LT)

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=52 * mm, bottomMargin=18 * mm, title="Fayol Project Intelligence Report")
    story = []
    pw = W - 30 * mm

    snap_data = [
        [Paragraph("PROJECT", sSectionSm), Paragraph(project_name, sBold), Paragraph("MODULES IN SCOPE", sSectionSm), Paragraph(modules, sBody)],
        [Paragraph("CURRENT PHASE", sSectionSm), Paragraph(current_phase, sBold), Paragraph("DATE GENERATED", sSectionSm), Paragraph(gen_date, sBody)],
        [Paragraph("PREPARED BY", sSectionSm), Paragraph("Fayol  SAP Project Automation", sBody), Paragraph("REPORT TYPE", sSectionSm), Paragraph("Implementation Forecast", sBody)],
    ]
    snap = Table(snap_data, colWidths=[35 * mm, 60 * mm, 40 * mm, 45 * mm], style=[("BACKGROUND", (0, 0), (-1, -1), GREY_LT), ("ROWBACKGROUNDS", (0, 0), (-1, -1), [GREY_LT, WHITE, GREY_LT]), ("LINEBELOW", (0, 0), (-1, -2), 0.5, GREY_LINE), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("ROUNDEDCORNERS", [4]), ("BOX", (0, 0), (-1, -1), 0.5, GREY_LINE)])
    story.append(snap)
    story.append(sp(16))

    story.append(HR(BLUE, 1.5, 0, 6))
    story.append(Paragraph("EXECUTIVE SUMMARY", sSection))
    story.append(sp(6))
    story.append(Paragraph(exec_summary, sBody))
    story.append(sp(16))

    story.append(HR(BLUE, 1.5, 0, 6))
    story.append(Paragraph("PROJECT HEALTH DASHBOARD", sSection))
    story.append(sp(8))

    def kpi_box(label, value, sub, bg, fg):
        return Table([[Paragraph(label, S("kl", fontName="Helvetica", fontSize=7, textColor=fg, leading=10, alignment=TA_CENTER))], [Paragraph(value, S("kv", fontName="Helvetica-Bold", fontSize=16, textColor=fg, leading=20, alignment=TA_CENTER))], [Paragraph(sub, S("ks", fontName="Helvetica", fontSize=7, textColor=fg, leading=10, alignment=TA_CENTER))]], colWidths=[pw / 5 - 3 * mm], style=[("BACKGROUND", (0, 0), (-1, -1), bg), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8), ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("ROUNDEDCORNERS", [5]), ("BOX", (0, 0), (-1, -1), 0.5, GREY_LINE)])

    kpis = [
        kpi_box("OVERALL HEALTH", health, "Project Status", health_bg, health_color),
        kpi_box("GO-LIVE", predicted_gl, "Predicted", RED_LT, RED),
        kpi_box("VARIANCE", f"+{variance_days} days", "Schedule Slip", RED_LT, RED),
        kpi_box("UAT COMPLETION", f"{uat_pct}%", "Current Progress", BLUE_LIGHT, BLUE),
        kpi_box("CONFIDENCE", f"{confidence}%", "Go-Live Forecast", AMBER_LT, AMBER),
    ]
    kpi_row = Table([kpis], colWidths=[pw / 5] * 5, style=[("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2)])
    story.append(kpi_row)
    story.append(sp(16))

    fc_data = [[
        Table([[Paragraph("ORIGINAL GO-LIVE", sSectionSm)], [Paragraph(original_gl, S("og", fontName="Helvetica-Bold", fontSize=14, textColor=GREY_DARK, leading=18))]], style=[("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LEFTPADDING", (0, 0), (-1, -1), 8)]),
        Table([[Paragraph("PREDICTED GO-LIVE", sSectionSm)], [Paragraph(predicted_gl, S("pg", fontName="Helvetica-Bold", fontSize=14, textColor=RED, leading=18))]], style=[("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LEFTPADDING", (0, 0), (-1, -1), 8)]),
        Table([[Paragraph("VARIANCE", sSectionSm)], [Paragraph(f"+{variance_days} days", S("var", fontName="Helvetica-Bold", fontSize=14, textColor=RED, leading=18))]], style=[("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LEFTPADDING", (0, 0), (-1, -1), 8)]),
        Table([[Paragraph("CONFIDENCE", sSectionSm)], [Paragraph(f"{confidence}%", S("conf", fontName="Helvetica-Bold", fontSize=14, textColor=AMBER, leading=18))]], style=[("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LEFTPADDING", (0, 0), (-1, -1), 8)]),
    ]]
    fc = Table(fc_data, colWidths=[pw / 4] * 4, style=[("BACKGROUND", (0, 0), (-1, -1), GREY_LT), ("BOX", (0, 0), (-1, -1), 0.5, GREY_LINE), ("LINEBEFORE", (1, 0), (-1, -1), 0.5, GREY_LINE), ("ROUNDEDCORNERS", [4])])
    recovery = Paragraph(f"<b>Recovery path:</b> {recovery_path}", S("rec", fontName="Helvetica", fontSize=9, textColor=GREY_DARK, leading=14, backColor=AMBER_LT, borderPadding=(8, 10, 8, 10)))
    story.append(KeepTogether([HR(BLUE, 1.5, 0, 6), Paragraph("GO-LIVE FORECAST", sSection), sp(8), fc, sp(8), recovery, sp(10)]))

    if milestones:
        chart_buf = make_variance_chart(milestones, 130, 85)
        chart_img = Image(chart_buf, width=130 * mm, height=85 * mm)
        chart_tbl = Table([[chart_img]], colWidths=[pw], style=[("ALIGN", (0, 0), (-1, -1), "CENTER"), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)])
        story.append(KeepTogether([HR(BLUE, 1.5, 0, 6), Paragraph("SCHEDULE VARIANCE CHART", sSection), sp(8), chart_tbl, sp(4), Paragraph("Each phase shows planned duration (blue) against actual delay in days (coloured by severity). Green bars indicate completed phases. Red indicates high-delay phases still in progress. Amber indicates moderate delay.", S("cap", fontName="Helvetica", fontSize=8, textColor=GREY_MID, leading=12)), sp(14)]))

    if milestones:
        hdr = ["PHASE", "PLAN START", "PLAN END", "ACTUAL END", "PREDICTED END", "VAR", "STATUS"]
        m_rows = [[Paragraph(h, S("mh", fontName="Helvetica-Bold", fontSize=8, textColor=WHITE, leading=11)) for h in hdr]]
        for milestone in milestones:
            sc, slc, stxt = status_color(milestone.get("status", ""))
            ae = milestone.get("actualEnd") or "Not Started"
            m_rows.append([
                Paragraph(milestone.get("phase", ""), sBody),
                Paragraph(milestone.get("planStart", ""), sBodySm),
                Paragraph(milestone.get("planEnd", ""), sBodySm),
                Paragraph(ae, S("ae", fontName="Helvetica", fontSize=8, textColor=GREEN if ae not in ["", "Not Started"] else GREY_MID, leading=12)),
                Paragraph(milestone.get("predictedEnd", ""), S("pr", fontName="Helvetica-Bold", fontSize=8, textColor=sc, leading=12)),
                Paragraph(f"+{milestone.get('varianceDays', 0)}d", S("vr", fontName="Helvetica-Bold", fontSize=8, textColor=sc, leading=12)),
                Paragraph(stxt, S("st", fontName="Helvetica-Bold", fontSize=7, textColor=sc, leading=11)),
            ])
        row_bgs = [("BACKGROUND", (0, i), (-1, i), GREY_LT if i % 2 == 0 else WHITE) for i in range(1, len(m_rows))]
        mt = Table(m_rows, colWidths=[38 * mm, 20 * mm, 20 * mm, 22 * mm, 24 * mm, 14 * mm, 22 * mm], style=[("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#07090F")), *row_bgs, ("LINEBELOW", (0, 0), (-1, -1), 0.5, GREY_LINE), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("BOX", (0, 0), (-1, -1), 0.5, GREY_LINE)])
        story.append(KeepTogether([HR(BLUE, 1.5, 0, 6), Paragraph("MILESTONE TRACKER", sSection), sp(8), mt, sp(14)]))

    if forecasts:
        story.append(KeepTogether([HR(BLUE, 1.5, 0, 6), Paragraph("AI FORECAST  MILESTONE BY MILESTONE", sSection), sp(8)]))
        for forecast_item in forecasts:
            status = forecast_item.get("status", "")
            conf = forecast_item.get("confidence", 0)
            phase = forecast_item.get("phase", "")
            reason = forecast_item.get("reasoning", "")
            sc = GREEN if status == "Complete" else RED
            cf_col = "#00A86B" if conf >= 90 else ("#F5A623" if conf >= 50 else "#FF3B5C")
            status_table = Table(
                [
                    [Paragraph(f"<font color='{'#00A86B' if status == 'Complete' else '#FF3B5C'}'><b>{status}</b></font>", S("fs_status", fontName="Helvetica-Bold", fontSize=8, textColor=sc, leading=11, alignment=TA_RIGHT))],
                    [Paragraph(f"<font color='#64748B'>Confidence: </font><font color='{cf_col}'><b>{conf}%</b></font>", S("fs_conf", fontName="Helvetica", fontSize=8, textColor=GREY_MID, leading=11, alignment=TA_RIGHT))],
                ],
                colWidths=[38 * mm],
                style=[
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ],
            )
            row_data = [[
                Table(
                    [[
                        Paragraph(phase, S("fp", fontName="Helvetica-Bold", fontSize=10, textColor=GREY_DARK, leading=14)),
                        status_table,
                    ]],
                    colWidths=[pw - 20 * mm - 38 * mm, 38 * mm],
                    style=[
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ],
                )
            ]]
            f_header = Table(row_data, colWidths=[pw], style=[("BACKGROUND", (0, 0), (-1, -1), GREEN_LT if status == "Complete" else RED_LT), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12), ("LINEABOVE", (0, 0), (-1, 0), 2, sc)])
            f_body = Table([[Paragraph(reason, sBody)]], colWidths=[pw], style=[("BACKGROUND", (0, 0), (-1, -1), WHITE), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 10), ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12), ("BOX", (0, 0), (-1, -1), 0.5, GREY_LINE)])
            story.append(KeepTogether([f_header, f_body, sp(6)]))
        story.append(sp(10))

    if risks:
        sev_colors = {"Critical": RED, "High": ORANGE, "Medium": AMBER, "Low": GREY_MID}
        risk_hdr = [Paragraph(h, S("rh", fontName="Helvetica-Bold", fontSize=8, textColor=WHITE, leading=11)) for h in ["#", "SEVERITY", "RISK", "IMPACT", "OWNER", "ACTION REQUIRED"]]
        risk_rows = [risk_hdr]
        for risk in risks:
            sc = sev_colors.get(risk.get("severity", ""), GREY_MID)
            risk_number = str(risk.get("number", "")).strip()
            risk_number = risk_number if risk_number.upper().startswith("R") else f"R{risk_number}"
            risk_rows.append([
                Paragraph(risk_number, S("rn", fontName="Helvetica-Bold", fontSize=11, textColor=sc, leading=16, alignment=TA_CENTER)),
                Paragraph(risk.get("severity", ""), S("rs", fontName="Helvetica-Bold", fontSize=8, textColor=sc, leading=12)),
                Paragraph(f"<b>{risk.get('title', '')}</b>", sBody),
                Paragraph(risk.get("impact", ""), sBody),
                Paragraph(risk.get("owner", ""), sBodySm),
                Paragraph(risk.get("action", ""), sBody),
            ])
        risk_bgs = [("BACKGROUND", (0, i), (-1, i), GREY_LT if i % 2 == 0 else WHITE) for i in range(1, len(risk_rows))]
        rt = Table(risk_rows, colWidths=[12 * mm, 18 * mm, 40 * mm, 36 * mm, 22 * mm, pw - 128 * mm], style=[("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#07090F")), *risk_bgs, ("LINEBELOW", (0, 0), (-1, -1), 0.5, GREY_LINE), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("BOX", (0, 0), (-1, -1), 0.5, GREY_LINE)])
        story.append(KeepTogether([HR(RED, 1.5, 0, 6), Paragraph("TOP RISKS", S("rsec", fontName="Helvetica-Bold", fontSize=11, textColor=RED, leading=16)), sp(8), rt, sp(14)]))

    def action_table(label, items, bg, lc):
        rows = [[Paragraph(label, S("al", fontName="Helvetica-Bold", fontSize=8, textColor=WHITE, leading=11))]]
        for i, item in enumerate(items, 1):
            rows.append([Table([[
                Paragraph(str(i), S("an", fontName="Helvetica-Bold", fontSize=10, textColor=lc, leading=14, alignment=TA_CENTER)),
                Paragraph(item, sBody),
            ]], colWidths=[8 * mm, pw - 22 * mm], style=[("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")])])
        return Table(rows, colWidths=[pw], style=[("BACKGROUND", (0, 0), (-1, 0), bg), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, GREY_LT]), ("LINEBELOW", (0, 0), (-1, -1), 0.5, GREY_LINE), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8), ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12), ("BOX", (0, 0), (-1, -1), 0.5, GREY_LINE)])

    if actions_now or actions_month:
        at_now = action_table("THIS WEEK  IMMEDIATE", actions_now, RED, RED)
        at_month = action_table("THIS MONTH", actions_month, BLUE, BLUE)
        story.append(KeepTogether([HR(BLUE, 1.5, 0, 6), Paragraph("RECOMMENDED ACTIONS", sSection), sp(8), at_now, sp(8), at_month, sp(14)]))

    va_para = Paragraph(va_text_raw, sBody)
    va = Table([[va_para]], colWidths=[pw], style=[("BACKGROUND", (0, 0), (-1, -1), BLUE_LIGHT), ("TOPPADDING", (0, 0), (-1, -1), 12), ("BOTTOMPADDING", (0, 0), (-1, -1), 12), ("LEFTPADDING", (0, 0), (-1, -1), 14), ("RIGHTPADDING", (0, 0), (-1, -1), 14), ("LINEABOVE", (0, 0), (-1, 0), 2, BLUE), ("BOX", (0, 0), (-1, -1), 0.5, BLUE_MID)])

    if milestones:
        va2_buf = make_variance_analysis_chart(milestones, 140, 82)
        va2_img = Image(va2_buf, width=140 * mm, height=82 * mm)
        va2_tbl = Table([[va2_img]], colWidths=[pw], style=[("ALIGN", (0, 0), (-1, -1), "CENTER"), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)])
        va2_caption = Paragraph("<b>Left chart:</b> Delay attribution by root cause  external vs internal factors. <b>Right chart:</b> Cumulative delay build-up across project phases. Green dots mark completed phases; red dots mark phases still at risk.", S("cap2", fontName="Helvetica", fontSize=8, textColor=GREY_MID, leading=12))
        story.append(KeepTogether([HR(BLUE, 1.5, 0, 6), Paragraph("VARIANCE ANALYSIS", sSection), sp(6), va, sp(10), va2_tbl, sp(4), va2_caption, sp(14)]))
    else:
        story.append(KeepTogether([HR(BLUE, 1.5, 0, 6), Paragraph("VARIANCE ANALYSIS", sSection), sp(6), va, sp(14)]))

    story.append(HR(GREY_LINE, 0.5, 4, 4))
    story.append(Paragraph("This report was generated by Fayol  SAP Project Automation. Plan dates are locked at project import and cannot be modified. All revised dates and remarks are audit-logged with timestamps. This document is confidential and intended solely for the named project stakeholders.", S("fn", fontName="Helvetica", fontSize=7, textColor=GREY_MID, leading=11, alignment=TA_CENTER)))

    doc.build(story, onFirstPage=partial(on_page, project_name=project_name, generated_date=gen_date), onLaterPages=partial(on_page, project_name=project_name, generated_date=gen_date))
    buf.seek(0)
    return buf.read()


ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
SUPPORT_AI_SYSTEM_PROMPT = (
    "You are Fayol AMS PM. Generate concise, professional support portfolio narrative for executive stakeholders. "
    "Use only the provided data, avoid hype, and keep recommendations practical."
)


def format_support_display_date(value: str) -> str:
    if not value:
        return "-"
    text = str(value).strip()
    candidates = [text, text.replace("Z", "+00:00"), text.split("T")[0]]
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed.strftime("%d %b %Y")
        except ValueError:
            continue
    for pattern in ("%Y-%m-%d", "%d %b %Y", "%d %b %y"):
        try:
            parsed = datetime.strptime(text[:10], pattern)
            return parsed.strftime("%d %b %Y")
        except ValueError:
            continue
    return text


def support_ticket_type(ticket: dict) -> str:
    normalized = str(ticket.get("normalizedType") or "").strip()
    raw = str(ticket.get("type") or "").strip().lower()
    if normalized in {"Incidents", "Change Requests", "L1 Support"}:
        return normalized
    if raw in {"break-fix", "incident", "incidents"}:
        return "Incidents"
    if raw in {"enhancement", "cr", "change request", "change requests"}:
        return "Change Requests"
    return normalized or "Other"


def support_ticket_status(ticket: dict) -> str:
    status = str(ticket.get("analyticsStatus") or ticket.get("normalizedStatus") or ticket.get("status") or "").strip()
    mapping = {"Resolved": "Closed", "Pending SAP": "Pending Internal", "In Progress": "Open"}
    normalized = mapping.get(status, status or "Open")
    if normalized not in {"Closed", "Open", "Pending Customer", "Pending Internal"}:
        return "Open"
    return normalized


def support_is_closed(ticket: dict) -> bool:
    return support_ticket_status(ticket) == "Closed"


def make_support_monthly_trend_chart(monthly_trend: List[dict], width_mm: float, height_mm: float):
    trend_rows = monthly_trend or [{"month": "-", "created": 0, "resolved": 0}]
    months = [row.get("month", "-") for row in trend_rows]
    created = [row.get("created", 0) for row in trend_rows]
    resolved = [row.get("resolved", 0) for row in trend_rows]

    fig, ax = plt.subplots(figsize=(width_mm / 25.4, height_mm / 25.4), facecolor="#F1F5F9")
    ax.set_facecolor("#F1F5F9")
    x = np.arange(len(months))

    ax.plot(x, created, color="#0A84FF", linewidth=2.4, marker="o", markersize=4.5, markerfacecolor="white", markeredgewidth=1.8)
    ax.plot(x, resolved, color="#00A86B", linewidth=2.4, marker="o", markersize=4.5, markerfacecolor="white", markeredgewidth=1.8)
    ax.fill_between(x, created, alpha=0.08, color="#0A84FF")
    ax.fill_between(x, resolved, alpha=0.08, color="#00A86B")
    ax.set_xticks(x)
    ax.set_xticklabels(months, fontsize=7, color="#2C3E50")
    ax.tick_params(axis="y", labelsize=7, colors="#64748B")
    ax.tick_params(axis="x", length=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#E2E8F0")
    ax.spines["bottom"].set_color("#E2E8F0")
    ax.yaxis.grid(True, color="#E2E8F0", linestyle="--", linewidth=0.5)
    ax.set_axisbelow(True)
    ax.set_ylabel("Tickets", fontsize=7, color="#64748B")
    ax.set_title("Monthly Ticket Trend  Created vs Resolved", fontsize=8, color="#2C3E50", pad=10, fontweight="bold")
    created_patch = mpatches.Patch(color="#0A84FF", label="Created")
    resolved_patch = mpatches.Patch(color="#00A86B", label="Resolved")
    ax.legend(handles=[created_patch, resolved_patch], fontsize=6.5, loc="upper left", framealpha=0.8, edgecolor="#E2E8F0")
    plt.tight_layout(pad=0.8)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=180, bbox_inches="tight", facecolor="#F1F5F9")
    plt.close(fig)
    buf.seek(0)
    return buf


def fallback_support_executive_summary(data: dict) -> str:
    total = data.get("totalTickets", 0)
    sla = data.get("slaCompliance", 0)
    breached = data.get("breachedTickets", 0)
    hotspot = data.get("moduleHotspot") or "the current support portfolio"
    top_aging = data.get("topAgingTicket") or {}
    trend = data.get("monthlyTrend") or []
    latest = trend[-1] if trend else {"created": 0, "resolved": 0}
    flow_statement = (
        "Resolution throughput kept pace with intake this period."
        if latest.get("resolved", 0) >= latest.get("created", 0)
        else "Resolution throughput is trailing intake and needs recovery attention."
    )
    aging_statement = (
        f"The biggest current risk is ticket {top_aging.get('id', '-')}, which has been open for {top_aging.get('ageDays', 0)} days for {top_aging.get('client', 'the client')}."
        if top_aging.get("id")
        else "The current portfolio risk is concentrated in the oldest unresolved support backlog."
    )
    return (
        f"The support portfolio closed the period with {total} tickets in view, with SLA compliance at {sla}% and {breached} breached items requiring management attention. "
        f"Current demand is most concentrated in {hotspot}. "
        f"{aging_statement} "
        f"{flow_statement}"
    )


def fallback_support_sla_analysis(data: dict) -> str:
    total = max(1, data.get("totalTickets", 0))
    violated = data.get("slaViolated", 0)
    within = max(0, total - violated)
    compliance = data.get("slaCompliance", 0)
    critical_open = data.get("criticalOpen", 0)
    high_open = data.get("highOpen", 0)
    return (
        f"{within} tickets are currently within SLA and {violated} tickets are outside SLA, leaving overall compliance at {compliance}%. "
        f"Pressure remains highest in the unresolved priority queue, with {critical_open} critical and {high_open} high-priority tickets still open. "
        f"The immediate focus should stay on reducing breach volume before new backlog enters the queue."
    )


def fallback_support_actions(data: dict) -> dict:
    hotspot = data.get("moduleHotspot") or "the primary hotspot module"
    top_aging = data.get("topAgingTicket") or {}
    actions_now = [
        f"Run a focused daily triage on {hotspot} tickets until breach volume stabilizes.",
        f"Review ticket {top_aging.get('id', 'the top aging ticket')} with the assigned consultant and client owner to confirm the next unblocker.",
        "Escalate any critical or high-priority tickets with no same-day progress update.",
    ]
    actions_month = [
        "Rebalance consultant capacity toward the highest-open modules and breach clusters.",
        "Review client-side waiting points and convert repeated pending patterns into standard resolution playbooks.",
        "Use the last 6 months of trend data to reset SLA recovery targets and throughput expectations.",
    ]
    return {"actionsNow": actions_now, "actionsMonth": actions_month}


def call_anthropic_text(system_prompt: str, user_prompt: str, max_tokens: int = 800) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")

    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": [{"type": "text", "text": user_prompt}]}],
    }
    request = urllib.request.Request(
        ANTHROPIC_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Anthropic API request failed: {exc.code} {detail[:240]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Anthropic API connection failed: {exc.reason}") from exc

    content_blocks = response_payload.get("content") or []
    text = "\n".join(block.get("text", "") for block in content_blocks if block.get("type") == "text").strip()
    if not text:
        raise RuntimeError("Anthropic API returned no text content")
    return text


def parse_support_actions(text: str) -> dict:
    candidate = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", candidate, flags=re.S)
    if fenced:
        candidate = fenced.group(1).strip()
    if not candidate.startswith("{"):
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end != -1:
            candidate = candidate[start : end + 1]
    parsed = json.loads(candidate)
    actions_now = [str(item).strip() for item in parsed.get("actionsNow", []) if str(item).strip()]
    actions_month = [str(item).strip() for item in parsed.get("actionsMonth", []) if str(item).strip()]
    return {"actionsNow": actions_now, "actionsMonth": actions_month}


def build_support_ai_context(data: dict) -> dict:
    return {
        "reportDate": data.get("reportDate"),
        "periodStart": data.get("periodStart"),
        "periodEnd": data.get("periodEnd"),
        "clientFilter": data.get("clientFilter"),
        "totalTickets": data.get("totalTickets"),
        "openIncidents": data.get("openIncidents"),
        "closedIncidents": data.get("closedIncidents"),
        "pendingCustomer": data.get("pendingCustomer"),
        "pendingInternal": data.get("pendingInternal"),
        "openCRs": data.get("openCRs"),
        "closedCRs": data.get("closedCRs"),
        "slaCompliance": data.get("slaCompliance"),
        "slaViolated": data.get("slaViolated"),
        "avgResolutionHrs": data.get("avgResolutionHrs"),
        "csatAvg": data.get("csatAvg"),
        "criticalOpen": data.get("criticalOpen"),
        "highOpen": data.get("highOpen"),
        "breachedTickets": data.get("breachedTickets"),
        "moduleHotspot": data.get("moduleHotspot"),
        "topAgingTicket": data.get("topAgingTicket"),
        "monthlyTrend": data.get("monthlyTrend", []),
        "moduleBreakdown": data.get("moduleBreakdown", []),
    }


def generate_support_ai_sections(data: dict) -> dict:
    context = build_support_ai_context(data)
    context_json = json.dumps(context, indent=2)
    summary_text = fallback_support_executive_summary(data)
    sla_text = fallback_support_sla_analysis(data)
    fallback_actions = fallback_support_actions(data)
    actions_now = fallback_actions["actionsNow"]
    actions_month = fallback_actions["actionsMonth"]

    try:
        summary_text = call_anthropic_text(
            SUPPORT_AI_SYSTEM_PROMPT,
            "Write a 3-4 sentence executive summary for the AMS support portfolio. Cover overall health, the biggest risk, and the most important achievement.\n\n"
            f"Data:\n{context_json}",
            max_tokens=250,
        )
    except Exception:
        pass

    try:
        sla_text = call_anthropic_text(
            SUPPORT_AI_SYSTEM_PROMPT,
            "Write one concise paragraph explaining the current SLA compliance trend for the AMS support portfolio. Focus on breach pressure, ticket mix, and what needs attention.\n\n"
            f"Data:\n{context_json}",
            max_tokens=220,
        )
    except Exception:
        pass

    try:
        actions_response = call_anthropic_text(
            SUPPORT_AI_SYSTEM_PROMPT,
            "Return valid JSON only with keys actionsNow and actionsMonth. Each value must be an array of 3 concise, actionable recommendations for the AMS support manager.\n\n"
            f"Data:\n{context_json}",
            max_tokens=320,
        )
        parsed_actions = parse_support_actions(actions_response)
        if parsed_actions["actionsNow"]:
            actions_now = parsed_actions["actionsNow"]
        if parsed_actions["actionsMonth"]:
            actions_month = parsed_actions["actionsMonth"]
    except Exception:
        pass

    return {
        "executiveSummary": summary_text.strip(),
        "slaAnalysis": sla_text.strip(),
        "actionsNow": actions_now,
        "actionsMonth": actions_month,
    }


def generate_support_pdf(data: dict) -> bytes:
    buf = io.BytesIO()
    client_filter = data.get("clientFilter", "All Support Projects")
    report_date = format_support_display_date(data.get("reportDate", ""))
    period_start = format_support_display_date(data.get("periodStart", ""))
    period_end = format_support_display_date(data.get("periodEnd", ""))
    total_tickets = data.get("totalTickets", 0)
    open_incidents = data.get("openIncidents", 0)
    closed_incidents = data.get("closedIncidents", 0)
    pending_customer = data.get("pendingCustomer", 0)
    pending_internal = data.get("pendingInternal", 0)
    open_crs = data.get("openCRs", 0)
    closed_crs = data.get("closedCRs", 0)
    sla_compliance = data.get("slaCompliance", 0)
    sla_violated = data.get("slaViolated", 0)
    avg_resolution = float(data.get("avgResolutionHrs", 0) or 0)
    csat_avg = float(data.get("csatAvg", 0) or 0)
    breached_tickets = data.get("breachedTickets", 0)
    tickets = data.get("tickets", [])
    consultants = data.get("consultants", [])
    monthly_trend = data.get("monthlyTrend", [])
    module_breakdown = sorted(data.get("moduleBreakdown", []), key=lambda item: item.get("open", 0), reverse=True)
    executive_summary = data.get("executiveSummary") or fallback_support_executive_summary(data)
    sla_analysis = data.get("slaAnalysis") or fallback_support_sla_analysis(data)
    fallback_actions = fallback_support_actions(data)
    actions_now = data.get("actionsNow") or fallback_actions["actionsNow"]
    actions_month = data.get("actionsMonth") or fallback_actions["actionsMonth"]

    incident_counts = {"Closed": 0, "Open": 0, "Pending Customer": 0, "Pending Internal": 0}
    cr_counts = {"Closed": 0, "Open": 0, "Pending Customer": 0, "Pending Internal": 0}
    for ticket in tickets:
        counts = cr_counts if support_ticket_type(ticket) == "Change Requests" else incident_counts
        counts[support_ticket_status(ticket)] += 1

    aging_rows = sorted(
        [ticket for ticket in tickets if not support_is_closed(ticket) and int(ticket.get("ageDays", 0) or 0) >= 3],
        key=lambda item: int(item.get("ageDays", 0) or 0),
        reverse=True,
    )[:10]
    cr_pipeline_rows = sorted(
        [ticket for ticket in tickets if support_ticket_type(ticket) == "Change Requests" and not support_is_closed(ticket)],
        key=lambda item: int(item.get("pendingAgeDays", item.get("ageDays", 0)) or 0),
        reverse=True,
    )[:10]
    consultant_rows = sorted(consultants, key=lambda item: item.get("ticketsHandled", 0), reverse=True)
    total_open_module = max(1, sum(item.get("open", 0) for item in module_breakdown))

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=52 * mm,
        bottomMargin=18 * mm,
        title="Fayol AMS Support Intelligence Report",
    )
    story = []
    pw = W - 30 * mm

    snapshot_rows = [
        [Paragraph("CLIENT", sSectionSm), Paragraph(client_filter, sBold), Paragraph("PERIOD", sSectionSm), Paragraph(f"{period_start} - {period_end}", sBody)],
        [Paragraph("DATE GENERATED", sSectionSm), Paragraph(report_date, sBody), Paragraph("REPORT TYPE", sSectionSm), Paragraph("AMS Support Intelligence", sBody)],
    ]
    snapshot = Table(
        snapshot_rows,
        colWidths=[35 * mm, 60 * mm, 35 * mm, 50 * mm],
        style=[
            ("BACKGROUND", (0, 0), (-1, -1), GREY_LT),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [GREY_LT, WHITE]),
            ("LINEBELOW", (0, 0), (-1, -2), 0.5, GREY_LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("BOX", (0, 0), (-1, -1), 0.5, GREY_LINE),
        ],
    )
    story.append(snapshot)
    story.append(sp(16))

    story.append(HR(BLUE, 1.5, 0, 6))
    story.append(Paragraph("EXECUTIVE SUMMARY", sSection))
    story.append(sp(6))
    story.append(Paragraph(executive_summary, sBody))
    story.append(sp(16))

    story.append(HR(BLUE, 1.5, 0, 6))
    story.append(Paragraph("SUPPORT KPI DASHBOARD", sSection))
    story.append(sp(8))

    def kpi_box(label, value, sub, bg, fg):
        return Table(
            [
                [Paragraph(label, S("support_kl", fontName="Helvetica", fontSize=7, textColor=fg, leading=10, alignment=TA_CENTER))],
                [Paragraph(value, S("support_kv", fontName="Helvetica-Bold", fontSize=15, textColor=fg, leading=18, alignment=TA_CENTER))],
                [Paragraph(sub, S("support_ks", fontName="Helvetica", fontSize=7, textColor=fg, leading=10, alignment=TA_CENTER))],
            ],
            colWidths=[pw / 6 - 2 * mm],
            style=[
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("BOX", (0, 0), (-1, -1), 0.5, GREY_LINE),
            ],
        )

    kpi_row = Table(
        [[
            kpi_box("TOTAL TICKETS", str(total_tickets), "Portfolio volume", BLUE_LIGHT, BLUE),
            kpi_box("OPEN INCIDENTS", str(open_incidents), "Current incident load", RED_LT if open_incidents else GREEN_LT, RED if open_incidents else GREEN),
            kpi_box("SLA COMPLIANCE", f"{sla_compliance}%", "Current compliance", GREEN_LT if sla_compliance >= 90 else AMBER_LT, GREEN if sla_compliance >= 90 else AMBER),
            kpi_box("AVG RESOLUTION", f"{avg_resolution:.1f}h", "Resolved tickets", BLUE_LIGHT, BLUE),
            kpi_box("CSAT", f"{csat_avg:.1f}" if csat_avg else "-", "Average score", GREEN_LT if csat_avg >= 4.3 else AMBER_LT, GREEN if csat_avg >= 4.3 else AMBER),
            kpi_box("BREACHED SLA", str(breached_tickets), "Open risk count", RED_LT, RED),
        ]],
        colWidths=[pw / 6] * 6,
        style=[("LEFTPADDING", (0, 0), (-1, -1), 1), ("RIGHTPADDING", (0, 0), (-1, -1), 1)],
    )
    story.append(kpi_row)
    story.append(sp(16))

    status_rows = [
        [Paragraph(h, S("support_sh", fontName="Helvetica-Bold", fontSize=8, textColor=WHITE, leading=11)) for h in ["TYPE", "CLOSED", "OPEN", "PENDING CUSTOMER", "PENDING INTERNAL"]],
        [Paragraph("Incidents", sBody), Paragraph(str(incident_counts["Closed"]), sBold), Paragraph(str(incident_counts["Open"]), sBold), Paragraph(str(incident_counts["Pending Customer"]), sBold), Paragraph(str(incident_counts["Pending Internal"]), sBold)],
        [Paragraph("Change Requests", sBody), Paragraph(str(cr_counts["Closed"]), sBold), Paragraph(str(cr_counts["Open"]), sBold), Paragraph(str(cr_counts["Pending Customer"]), sBold), Paragraph(str(cr_counts["Pending Internal"]), sBold)],
    ]
    status_table = Table(
        status_rows,
        colWidths=[45 * mm, 28 * mm, 28 * mm, 42 * mm, 42 * mm],
        style=[
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#07090F")),
            ("BACKGROUND", (0, 1), (-1, 1), GREY_LT),
            ("BACKGROUND", (0, 2), (-1, 2), WHITE),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, GREY_LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("BOX", (0, 0), (-1, -1), 0.5, GREY_LINE),
        ],
    )
    story.append(HR(BLUE, 1.5, 0, 6))
    story.append(Paragraph("TICKET STATUS OVERVIEW", sSection))
    story.append(sp(8))
    story.append(status_table)
    story.append(PageBreak())

    within_sla = max(0, total_tickets - sla_violated)
    within_pct = int(round((within_sla / max(1, total_tickets)) * 100))
    violated_pct = int(round((sla_violated / max(1, total_tickets)) * 100))
    sla_split = Table(
        [[
            Table(
                [[Paragraph("WITHIN SLA", S("support_sla_w_label", fontName="Helvetica-Bold", fontSize=9, textColor=GREEN, leading=12))], [Paragraph(f"{within_sla} tickets ({within_pct}%)", S("support_sla_w_value", fontName="Helvetica-Bold", fontSize=15, textColor=GREEN, leading=18))]],
                colWidths=[pw / 2 - 6 * mm],
                style=[("BACKGROUND", (0, 0), (-1, -1), GREEN_LT), ("BOX", (0, 0), (-1, -1), 0.5, GREY_LINE), ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10), ("LEFTPADDING", (0, 0), (-1, -1), 12)],
            ),
            Table(
                [[Paragraph("SLA VIOLATED", S("support_sla_v_label", fontName="Helvetica-Bold", fontSize=9, textColor=RED, leading=12))], [Paragraph(f"{sla_violated} tickets ({violated_pct}%)", S("support_sla_v_value", fontName="Helvetica-Bold", fontSize=15, textColor=RED, leading=18))]],
                colWidths=[pw / 2 - 6 * mm],
                style=[("BACKGROUND", (0, 0), (-1, -1), RED_LT), ("BOX", (0, 0), (-1, -1), 0.5, GREY_LINE), ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10), ("LEFTPADDING", (0, 0), (-1, -1), 12)],
            ),
        ]],
        colWidths=[pw / 2, pw / 2],
        style=[("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2)],
    )
    story.append(HR(BLUE, 1.5, 0, 6))
    story.append(Paragraph("SLA COMPLIANCE ANALYSIS", sSection))
    story.append(sp(8))
    story.append(sla_split)
    story.append(sp(8))
    story.append(Paragraph(sla_analysis, sBody))
    story.append(sp(14))

    module_rows = [[Paragraph(h, S("support_mh", fontName="Helvetica-Bold", fontSize=8, textColor=WHITE, leading=11)) for h in ["MODULE", "OPEN", "CRITICAL", "% OF OPEN"]]]
    for item in module_breakdown[:8]:
        share = int(round((item.get("open", 0) / total_open_module) * 100))
        module_rows.append([Paragraph(item.get("module", "-"), sBody), Paragraph(str(item.get("open", 0)), sBold), Paragraph(str(item.get("critical", 0)), S("support_mc", fontName="Helvetica-Bold", fontSize=9, textColor=RED if item.get("critical", 0) else GREY_DARK, leading=12)), Paragraph(f"{share}%", sBodySm)])
    module_table = Table(
        module_rows,
        colWidths=[70 * mm, 25 * mm, 25 * mm, 35 * mm],
        style=[
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#07090F")),
            *[("BACKGROUND", (0, idx), (-1, idx), GREY_LT if idx % 2 == 1 else WHITE) for idx in range(1, len(module_rows))],
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, GREY_LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("BOX", (0, 0), (-1, -1), 0.5, GREY_LINE),
        ],
    )
    story.append(HR(BLUE, 1.5, 0, 6))
    story.append(Paragraph("MODULE HOTSPOT ANALYSIS", sSection))
    story.append(sp(8))
    story.append(module_table)
    story.append(sp(14))

    trend_chart = Image(make_support_monthly_trend_chart(monthly_trend, 135, 78), width=135 * mm, height=78 * mm)
    trend_table = Table([[trend_chart]], colWidths=[pw], style=[("ALIGN", (0, 0), (-1, -1), "CENTER")])
    story.append(HR(BLUE, 1.5, 0, 6))
    story.append(Paragraph("MONTHLY TREND", sSection))
    story.append(sp(8))
    story.append(trend_table)
    story.append(PageBreak())

    aging_table_rows = [[Paragraph(h, S("support_ah", fontName="Helvetica-Bold", fontSize=8, textColor=WHITE, leading=11)) for h in ["TICKET", "SUBJECT", "CLIENT", "MODULE", "AGE", "SLA"]]]
    for ticket in aging_rows:
        aging_table_rows.append([
            Paragraph(ticket.get("id", "-"), sBold),
            Paragraph(ticket.get("title", "-"), sBody),
            Paragraph(ticket.get("clientDisplayName") or ticket.get("clientName") or ticket.get("client", "-"), sBodySm),
            Paragraph(ticket.get("module", "-"), sBodySm),
            Paragraph(f"{int(ticket.get('ageDays', 0) or 0)}d", S("support_age", fontName="Helvetica-Bold", fontSize=8, textColor=RED if ticket.get("breached") else GREY_DARK, leading=12)),
            Paragraph("Breached" if ticket.get("breached") else "At Risk", S("support_sla_status", fontName="Helvetica-Bold", fontSize=8, textColor=RED if ticket.get("breached") else AMBER, leading=12)),
        ])
    if len(aging_table_rows) == 1:
        aging_table_rows.append([Paragraph("No aged tickets", sBody), Paragraph("-", sBody), Paragraph("-", sBody), Paragraph("-", sBody), Paragraph("-", sBody), Paragraph("-", sBody)])
    aging_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#07090F")),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, GREY_LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 0.5, GREY_LINE),
    ]
    for idx in range(1, len(aging_table_rows)):
        ticket = aging_rows[idx - 1] if idx - 1 < len(aging_rows) else {}
        aging_styles.append(("BACKGROUND", (0, idx), (-1, idx), RED_LT if ticket.get("breached") else (GREY_LT if idx % 2 == 1 else WHITE)))
    aging_table = Table(aging_table_rows, colWidths=[22 * mm, 72 * mm, 32 * mm, 24 * mm, 15 * mm, 20 * mm], style=aging_styles)
    story.append(HR(RED, 1.5, 0, 6))
    story.append(Paragraph("AGING & ESCALATION RISK", S("support_asec", fontName="Helvetica-Bold", fontSize=11, textColor=RED, leading=16)))
    story.append(sp(8))
    story.append(aging_table)
    story.append(sp(14))

    cr_table_rows = [[Paragraph(h, S("support_ch", fontName="Helvetica-Bold", fontSize=8, textColor=WHITE, leading=11)) for h in ["TICKET", "SUBJECT", "MODULE", "CLIENT", "EFFORT HRS", "PENDING SINCE", "AGE"]]]
    for ticket in cr_pipeline_rows:
        pending_since = format_support_display_date(ticket.get("pendingSince") or ticket.get("createdDate") or "")
        age_days = int(ticket.get("pendingAgeDays", ticket.get("ageDays", 0)) or 0)
        cr_table_rows.append([
            Paragraph(ticket.get("id", "-"), sBold),
            Paragraph(ticket.get("title", "-"), sBody),
            Paragraph(ticket.get("module", "-"), sBodySm),
            Paragraph(ticket.get("clientDisplayName") or ticket.get("clientName") or ticket.get("client", "-"), sBodySm),
            Paragraph(f"{float(ticket.get('effortHrs', 0) or 0):.1f}", sBodySm),
            Paragraph(pending_since, sBodySm),
            Paragraph(f"{age_days}d", S("support_cra", fontName="Helvetica-Bold", fontSize=8, textColor=RED if age_days > 3 else GREY_DARK, leading=12)),
        ])
    if len(cr_table_rows) == 1:
        cr_table_rows.append([Paragraph("No open change requests", sBody), Paragraph("-", sBody), Paragraph("-", sBody), Paragraph("-", sBody), Paragraph("-", sBody), Paragraph("-", sBody), Paragraph("-", sBody)])
    cr_table = Table(
        cr_table_rows,
        colWidths=[22 * mm, 62 * mm, 22 * mm, 28 * mm, 18 * mm, 28 * mm, 15 * mm],
        style=[
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#07090F")),
            *[("BACKGROUND", (0, idx), (-1, idx), GREY_LT if idx % 2 == 1 else WHITE) for idx in range(1, len(cr_table_rows))],
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, GREY_LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("BOX", (0, 0), (-1, -1), 0.5, GREY_LINE),
        ],
    )
    story.append(HR(BLUE, 1.5, 0, 6))
    story.append(Paragraph("CR PIPELINE STATUS", sSection))
    story.append(sp(8))
    story.append(cr_table)
    story.append(sp(14))

    consultant_table_rows = [[Paragraph(h, S("support_ph", fontName="Helvetica-Bold", fontSize=8, textColor=WHITE, leading=11)) for h in ["CONSULTANT", "TICKETS", "CLOSED", "SLA %", "CSAT", "AVG RES HRS"]]]
    for consultant in consultant_rows[:10]:
        consultant_table_rows.append([
            Paragraph(consultant.get("name", "-"), sBody),
            Paragraph(str(consultant.get("ticketsHandled", 0)), sBold),
            Paragraph(str(consultant.get("closedTickets", consultant.get("ticketsClosed", 0))), sBold),
            Paragraph(f"{consultant.get('slaCompliance', 0)}%", sBodySm),
            Paragraph(f"{float(consultant.get('csatAvg', 0) or 0):.1f}" if consultant.get("csatAvg") else "-", sBodySm),
            Paragraph(f"{float(consultant.get('avgResolutionHrs', 0) or 0):.1f}", sBodySm),
        ])
    if len(consultant_table_rows) == 1:
        consultant_table_rows.append([Paragraph("No consultant data", sBody), Paragraph("-", sBody), Paragraph("-", sBody), Paragraph("-", sBody), Paragraph("-", sBody), Paragraph("-", sBody)])
    consultant_table = Table(
        consultant_table_rows,
        colWidths=[55 * mm, 20 * mm, 20 * mm, 20 * mm, 20 * mm, 28 * mm],
        style=[
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#07090F")),
            *[("BACKGROUND", (0, idx), (-1, idx), GREY_LT if idx % 2 == 1 else WHITE) for idx in range(1, len(consultant_table_rows))],
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, GREY_LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("BOX", (0, 0), (-1, -1), 0.5, GREY_LINE),
        ],
    )
    story.append(HR(BLUE, 1.5, 0, 6))
    story.append(Paragraph("CONSULTANT PERFORMANCE SUMMARY", sSection))
    story.append(sp(8))
    story.append(consultant_table)
    story.append(PageBreak())

    def action_table(label, items, bg, lc):
        rows = [[Paragraph(label, S("support_al", fontName="Helvetica-Bold", fontSize=8, textColor=WHITE, leading=11))]]
        for idx, item in enumerate(items, 1):
            rows.append([Table([[Paragraph(str(idx), S("support_an", fontName="Helvetica-Bold", fontSize=10, textColor=lc, leading=14, alignment=TA_CENTER)), Paragraph(item, sBody)]], colWidths=[8 * mm, pw - 22 * mm], style=[("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")])])
        return Table(
            rows,
            colWidths=[pw],
            style=[
                ("BACKGROUND", (0, 0), (-1, 0), bg),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, GREY_LT]),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, GREY_LINE),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("BOX", (0, 0), (-1, -1), 0.5, GREY_LINE),
            ],
        )

    story.append(HR(BLUE, 1.5, 0, 6))
    story.append(Paragraph("RECOMMENDED ACTIONS", sSection))
    story.append(sp(8))
    story.append(action_table("THIS WEEK  IMMEDIATE", actions_now, RED, RED))
    story.append(sp(8))
    story.append(action_table("THIS MONTH", actions_month, BLUE, BLUE))
    story.append(sp(14))
    story.append(HR(GREY_LINE, 0.5, 4, 4))
    story.append(Paragraph("This report was generated by Fayol  SAP Project Automation. Ticket, SLA, and effort metrics are sourced from the current AMS support workspace. This document is confidential and intended solely for named support stakeholders.", S("support_fn", fontName="Helvetica", fontSize=7, textColor=GREY_MID, leading=11, alignment=TA_CENTER)))

    doc.build(
        story,
        onFirstPage=partial(on_support_page, project_name=client_filter, generated_date=report_date),
        onLaterPages=partial(on_support_page, project_name=client_filter, generated_date=report_date),
    )
    buf.seek(0)
    return buf.read()


def sanitize_filename(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", (value or "project").strip().lower()).strip("-")
    return normalized or "project"


app = FastAPI(title="Fayol Report API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/generate-report")
async def generate_report(payload: ReportRequest):
    pdf_bytes = generate_pdf(payload.model_dump())
    file_name = f'fayol-report-{sanitize_filename(payload.projectName)}.pdf'
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@app.post("/api/generate-support-report")
async def generate_support_report(payload: SupportReportRequest):
    report_data = payload.model_dump()
    report_data.update(generate_support_ai_sections(report_data))
    pdf_bytes = generate_support_pdf(report_data)
    file_name = f'fayol-support-report-{sanitize_filename(payload.reportDate)}.pdf'
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("report_api:app", host="0.0.0.0", port=8000, reload=True)
