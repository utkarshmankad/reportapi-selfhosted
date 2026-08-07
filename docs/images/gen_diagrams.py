"""One-off generator for the README architecture diagrams. Not part of the app."""
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.path import Path

plt.rcParams["font.family"] = "DejaVu Sans"

BG = "#0f172a"
CARD = "#1e293b"
CARD_ALT = "#1e3a5f"
BORDER = "#38bdf8"
BORDER_ALT = "#f59e0b"
TEXT = "#e2e8f0"
SUB = "#94a3b8"
ARROW = "#38bdf8"
ARROW_ALT = "#f59e0b"


def box(ax, x, y, w, h, title, subtitle=None, color=CARD, border=BORDER, fontsize=11):
    b = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        linewidth=1.8, edgecolor=border, facecolor=color, zorder=2,
    )
    ax.add_patch(b)
    ty = y + h / 2 + (0.12 if subtitle else 0)
    ax.text(x + w / 2, ty, title, ha="center", va="center",
             color=TEXT, fontsize=fontsize, fontweight="bold", zorder=3)
    if subtitle:
        ax.text(x + w / 2, y + h / 2 - 0.16, subtitle, ha="center", va="center",
                 color=SUB, fontsize=fontsize - 2.5, zorder=3)
    return (x, y, w, h)


def arrow(ax, p1, p2, color=ARROW, label=None, style="-|>", curve=0.0, lw=1.6):
    a = FancyArrowPatch(
        p1, p2, arrowstyle=style, mutation_scale=14,
        color=color, linewidth=lw, zorder=1,
        connectionstyle=f"arc3,rad={curve}",
    )
    ax.add_patch(a)
    if label:
        mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2 + curve * 0.6
        ax.text(mx, my, label, ha="center", va="center", color=SUB,
                 fontsize=8.5, zorder=3, backgroundcolor=BG)


def edge_point(box_xywh, side):
    x, y, w, h = box_xywh
    return {
        "top": (x + w / 2, y + h),
        "bottom": (x + w / 2, y),
        "left": (x, y + h / 2),
        "right": (x + w / 2 + w / 2, y + h / 2),
    }[side]


# ---------------------------------------------------------------- diagram 1
fig, ax = plt.subplots(figsize=(13, 8.2), dpi=200)
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
ax.set_xlim(0, 13)
ax.set_ylim(0, 8.2)
ax.axis("off")

ax.text(6.5, 7.85, "ReportAPI Self-Hosted — Architecture", ha="center", va="center",
         color=TEXT, fontsize=17, fontweight="bold")
ax.text(6.5, 7.5, "everything below runs on your own infrastructure via docker compose",
         ha="center", va="center", color=SUB, fontsize=10)

# External sources (top)
jira = box(ax, 0.5, 6.3, 2.2, 0.8, "Jira Cloud", "your instance", color=CARD_ALT, border=BORDER_ALT)
llm = box(ax, 10.3, 6.3, 2.2, 0.8, "LLM Provider", "OpenAI / Anthropic / Ollama", color=CARD_ALT, border=BORDER_ALT)

# Browser
browser = box(ax, 5.4, 6.3, 2.2, 0.8, "Your Browser", "localhost only", color=CARD_ALT, border=BORDER_ALT)

# Config UI
ui = box(ax, 5.4, 4.9, 2.2, 0.9, "Config UI", "Next.js · :8080", fontsize=10.5)

# API
api = box(ax, 5.15, 3.4, 2.7, 1.0, "FastAPI API", ":8000 · connectors, PII strip,\nprompt build, templates", fontsize=10.5)

# Worker/Beat
worker = box(ax, 1.6, 2.0, 2.3, 0.9, "Celery Worker", "runs scheduled reports")
beat = box(ax, 1.6, 0.8, 2.3, 0.9, "Celery Beat", "cron scheduler")

# Data stores
postgres = box(ax, 5.15, 0.8, 2.2, 0.9, "Postgres", "reports, schedules,\ntemplates, config")
redis = box(ax, 7.9, 2.0, 2.0, 0.9, "Redis", "Celery job queue")
chroma = box(ax, 7.9, 0.8, 2.0, 0.9, "Chroma", "embedded vector DB")

# Arrows
arrow(ax, edge_point(browser, "bottom"), edge_point(ui, "top"), label="HTTPS")
arrow(ax, edge_point(ui, "bottom"), edge_point(api, "top"), label="REST + X-Config-Token")
arrow(ax, edge_point(api, "left"), edge_point(jira, "bottom"), color=ARROW_ALT, curve=0.25, label="fetch tickets")
arrow(ax, edge_point(api, "right"), edge_point(llm, "bottom"), color=ARROW_ALT, curve=-0.25, label="PII-stripped prompt")
arrow(ax, (api[0] + 0.35, api[1]), (postgres[0] + 0.35, postgres[1] + postgres[3]), curve=0.0)
ax.text(api[0] + 0.1, 2.35, "persist\nreport", ha="right", va="center", color=SUB, fontsize=8.5)
arrow(ax, edge_point(api, "right"), edge_point(redis, "left"), curve=0.12, label="enqueue")
arrow(ax, (redis[0], redis[1] + 0.25), (worker[0] + worker[2], worker[1] + worker[3] - 0.25), color=ARROW, curve=0.06)
ax.text((redis[0] + worker[0] + worker[2]) / 2, 2.62, "consume", ha="center", va="center", color=SUB, fontsize=8.5, backgroundcolor=BG)
arrow(ax, edge_point(beat, "top"), edge_point(worker, "bottom"), label="trigger due\nschedules")
arrow(ax, (worker[0] + worker[2], worker[1] + 0.15), (postgres[0], postgres[1] + postgres[3] - 0.55), color=ARROW, curve=-0.2)
ax.text((worker[0] + worker[2] + postgres[0]) / 2, 1.15, "read schedules /\nwrite reports", ha="center", va="center", color=SUB, fontsize=8, backgroundcolor=BG)
arrow(ax, (redis[0] + redis[2] / 2, redis[1]), (chroma[0] + chroma[2] / 2, chroma[1] + chroma[3]), color=ARROW, curve=0.0, label="embeddings\n(optional)")

# legend / footnote
ax.text(0.5, 0.15, "Solid box = long-running container   ·   Orange = external network call   ·   All egress limited to Jira host + chosen LLM provider (SSRF-guarded)",
         color=SUB, fontsize=8, ha="left")

fig.tight_layout()
fig.savefig("docs/images/architecture.png", facecolor=BG)
plt.close(fig)

# ---------------------------------------------------------------- diagram 2
fig, ax = plt.subplots(figsize=(14, 7.6), dpi=200)
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
ax.set_xlim(0, 14)
ax.set_ylim(0, 7.6)
ax.axis("off")

ax.text(7, 7.3, "Report Generation Flow", ha="center", va="center",
         color=TEXT, fontsize=17, fontweight="bold")
ax.text(7, 6.95, "POST /api/report/generate  (same path for on-demand calls and Celery beat schedules)",
         ha="center", va="center", color=SUB, fontsize=9.5)

steps = [
    ("1", "Client / Beat", "calls the API\nwith board_id or sprint_id"),
    ("2", "Jira Connector", "fetches raw tickets\nover HTTPS"),
    ("3", "PII Stripper", "removes emails, names,\nIPs from every ticket"),
    ("4", "Prompt Builder", "assembles system +\nuser prompt, token-capped"),
    ("5", "LLM Provider", "OpenAI / Anthropic / Ollama\ngenerates the narrative"),
    ("6", "Template Renderer", "renders Markdown or\nPDF (WeasyPrint)"),
    ("7", "Postgres", "persists Report row,\nreturned to caller"),
]

n = len(steps)
x0, x1 = 1.2, 12.8
gap = (x1 - x0) / (n - 1)
y = 4.6
w, h = 1.55, 1.5

boxes = []
for i, (num, title, sub) in enumerate(steps):
    cx = x0 + gap * i
    b = box(ax, cx - w / 2, y - h / 2, w, h, f"{num}. {title}", sub, fontsize=9.5)
    boxes.append(b)

for i in range(n - 1):
    p1 = edge_point(boxes[i], "right")
    p1 = (boxes[i][0] + boxes[i][2], y)
    p2 = (boxes[i + 1][0], y)
    arrow(ax, p1, p2)

# PII note callout
ax.annotate(
    "raw ticket text never leaves\nstep 3 unmasked",
    xy=(x0 + gap * 2, y - h / 2), xytext=(x0 + gap * 2, y - h / 2 - 1.1),
    ha="center", color=BORDER_ALT, fontsize=8.5,
    arrowprops=dict(arrowstyle="-", color=BORDER_ALT, lw=1),
)

ax.text(6.5, 0.9,
        "Scheduled reports: Celery Beat reads the schedules table on its cron cadence and enqueues\n"
        "the same generation task onto the worker — no separate code path from an on-demand request.",
        ha="center", va="center", color=SUB, fontsize=9)

fig.tight_layout()
fig.savefig("docs/images/report_flow.png", facecolor=BG)
plt.close(fig)

print("wrote docs/images/architecture.png and docs/images/report_flow.png")
