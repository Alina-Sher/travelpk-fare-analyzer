"""CSS and small HTML snippets for the dashboard (navy / white / blue palette)."""
from __future__ import annotations

from html import escape

import streamlit as st

NAVY, BLUE, SKY, INK, MUTED, BORDER = "#0B2545", "#1565D8", "#F1F6FD", "#14213D", "#5B6B85", "#D5E0F0"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600;700&display=swap');
.stApp, [data-testid="stMarkdownContainer"] *, label, .stButton button, .stDownloadButton button {{
    font-family: 'Public Sans', system-ui, -apple-system, 'Segoe UI', sans-serif;
}}
.stApp {{ color: {INK}; }}
.block-container {{ padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1240px; }}
[data-testid="stSidebar"] {{ background: {SKY}; border-right: 1px solid {BORDER}; }}
.tp-brand {{ background: {NAVY}; color: #fff; border-radius: 8px; padding: .8rem 1rem; margin-bottom: 1rem; }}
.tp-brand .name {{ font-size: 1.25rem; font-weight: 700; letter-spacing: -.01em; }}
.tp-brand .tag {{ font-size: .8rem; color: #C9DAF5; margin-top: .1rem; }}
.tp-side-note {{ font-size: .75rem; color: {MUTED}; line-height: 1.45; margin-top: 1.2rem; }}
.tp-header {{ background: {NAVY}; border-radius: 10px; padding: 1.4rem 1.6rem; margin-bottom: .9rem; }}
.tp-title {{ color: #fff; font-size: 1.8rem; font-weight: 700; letter-spacing: -.015em; line-height: 1.2; }}
.tp-sub {{ color: #C9DAF5; font-size: 1rem; margin-top: .4rem; }}
.tp-banner {{ background: #FFF3CD; border: 1px solid #E5B93B; border-left: 6px solid #D99A00; color: #5C4000;
    padding: .75rem 1rem; border-radius: 8px; font-weight: 600; margin-bottom: 1rem; }}
.kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(175px, 1fr)); gap: .75rem; margin: .4rem 0 1.4rem; }}
.kpi {{ background: #fff; border: 1px solid {BORDER}; border-top: 4px solid {BLUE}; border-radius: 8px; padding: .8rem .95rem; }}
.kpi-label {{ font-size: .82rem; color: {MUTED}; font-weight: 600; }}
.kpi-value {{ font-size: 1.5rem; font-weight: 700; color: {NAVY}; line-height: 1.25; margin-top: .15rem; word-break: break-word; }}
.kpi-note {{ font-size: .75rem; color: {MUTED}; margin-top: .2rem; line-height: 1.35; }}
.route-name {{ font-weight: 700; color: {NAVY}; }}
@media (max-width: 640px) {{
    .tp-title {{ font-size: 1.35rem; }} .tp-header {{ padding: 1rem; }} .kpi-value {{ font-size: 1.3rem; }}
    .block-container {{ padding-left: 1rem; padding-right: 1rem; }}
}}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def sidebar_brand() -> str:
    return ('<div class="tp-brand"><div class="name">Travel.pk</div>'
            '<div class="tag">Flight Price Trend Analyzer</div></div>')


def header(title: str, subtitle: str) -> str:
    return f'<div class="tp-header"><div class="tp-title">{escape(title)}</div><div class="tp-sub">{escape(subtitle)}</div></div>'


def banner(text: str) -> str:
    return f'<div class="tp-banner" role="alert">{escape(text)}</div>'


def kpi_grid(cards: list[tuple[str, str, str, str]]) -> str:
    """cards = (label, value, note, tooltip)."""
    items = "".join(
        f'<div class="kpi" title="{escape(tip, quote=True)}"><div class="kpi-label">{escape(label)}</div>'
        f'<div class="kpi-value">{escape(value)}</div><div class="kpi-note">{escape(note)}</div></div>'
        for label, value, note, tip in cards
    )
    return f'<div class="kpi-grid">{items}</div>'
