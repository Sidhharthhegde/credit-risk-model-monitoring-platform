"""Institutional control-room presentation with an editorial type system."""

from __future__ import annotations

import html
from numbers import Integral
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


SEVERITY_COLORS = {
    "NORMAL": "#6F9B7A",
    "WARNING": "#C28A43",
    "CRITICAL": "#C45D54",
    "BLOCKED": "#773D49",
    "SYNTHETIC": "#7772A8",
    "NEUTRAL": "#5F7E98",
}

# Product voices are intentionally separate from governed severity colors.
LIFECYCLE_COLORS = {
    "INPUT": "#4BD6A2",
    "DRIFT": "#8A5CFF",
    "MODEL": "#5B7CFF",
    "OUTCOME": "#F7B84B",
    "ALERT": "#FF5B67",
    "LINEAGE": "#BFE6FF",
}


def inject_theme() -> None:
    st.markdown(
        """
        <style>
          @import url('https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap');

          @property --risk-counter {
            syntax: "<integer>";
            initial-value: 0;
            inherits: false;
          }

          :root {
            --risk-bg: #0b1016;
            --risk-panel: #111923;
            --risk-panel-raised: #151f2a;
            --risk-border: #2a333e;
            --risk-border-soft: #202832;
            --risk-text: #f2f0ea;
            --risk-muted: #9aa4b1;
            --risk-faint: #717c89;
            --risk-accent: #5f7e98;
            --risk-normal: #6f9b7a;
            --risk-warning: #c28a43;
            --risk-critical: #c45d54;
            --risk-blocked: #773d49;
            --risk-synthetic: #7772a8;
            --risk-shadow: 0 8px 20px rgba(0, 0, 0, .18);
            --voice-input: #4bd6a2;
            --voice-drift: #9a74e8;
            --voice-model: #5b7cff;
            --voice-outcome: #f7b84b;
            --voice-alert: #ff5b67;
            --voice-lineage: #bfe6ff;
            --voice-warm: #f7f4ee;
            --chapter-voice: #bfe6ff;
            --ease-authored: cubic-bezier(.16, 1, .3, 1);
          }

          html, body, [class*="css"] {
            color: var(--risk-text);
            font-family: "Inter", "Segoe UI", system-ui, sans-serif;
          }

          .stApp,
          [data-testid="stAppViewContainer"],
          [data-testid="stMain"] {
            background:
              radial-gradient(980px 620px at 76% -12%, rgba(191, 230, 255, .075), transparent 68%),
              linear-gradient(180deg, #090d12 0%, #0b1016 42%, #090d12 100%) !important;
            color: var(--risk-text) !important;
          }

          [data-testid="stHeader"] {
            background: rgba(11, 16, 22, .96) !important;
            border-bottom: 1px solid var(--risk-border-soft);
          }

          [data-testid="stMainBlockContainer"] {
            max-width: 1480px;
            padding: 2.35rem 3rem 5rem;
          }

          [data-testid="stSidebar"] {
            background: #0d131a !important;
            border-right: 1px solid var(--risk-border);
          }

          [data-testid="stSidebar"] > div:first-child {
            padding-top: 1.25rem;
          }

          [data-testid="stSidebarNav"] {
            display: none !important;
          }

          [data-testid="stSidebar"] h1 {
            font-size: 1.18rem !important;
            letter-spacing: .01em !important;
            color: #f4f7fb !important;
          }

          .risk-brand {
            display: flex;
            align-items: center;
            gap: .7rem;
            margin: .15rem 0 1.25rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--risk-border-soft);
          }
          .risk-brand i {
            position: relative;
            width: 2.2rem;
            height: 2.2rem;
            border: 1px solid rgba(191,230,255,.32);
            border-radius: 50%;
            background: conic-gradient(from 45deg, transparent 0 23%, var(--voice-model) 24% 27%, transparent 28% 55%, var(--voice-drift) 56% 59%, transparent 60%);
            box-shadow: inset 0 0 18px rgba(91,124,255,.12), 0 0 22px rgba(91,124,255,.08);
          }
          .risk-brand i::after { content:""; position:absolute; inset:.72rem; border-radius:50%; background:var(--voice-input); box-shadow:0 0 10px rgba(75,214,162,.5); }
          .risk-brand span, .risk-brand strong { display:block; }
          .risk-brand span { color:var(--voice-lineage); font:600 .58rem/1.2 "JetBrains Mono",Consolas,monospace; letter-spacing:.13em; }
          .risk-brand strong { margin-top:.22rem; color:#fff; font:400 .88rem/1 "Instrument Serif",Georgia,serif; letter-spacing:.04em; }

          [data-testid="stSidebar"] [role="radiogroup"] {
            display: none !important;
          }

          [data-testid="stSidebar"] input[type="radio"],
          [data-testid="stMain"] input[type="radio"] {
            position: absolute !important;
            width: 1px !important;
            height: 1px !important;
            margin: 0 !important;
            opacity: .01 !important;
          }
          [data-testid="stSidebar"] input[type="radio"] + div,
          [data-testid="stMain"] input[type="radio"] + div { opacity: 0 !important; width: 1px !important; }
          label[data-testid="stRadioOption"] > div > div > div:first-child {
            position: absolute !important;
            width: 1px !important;
            height: 1px !important;
            overflow: hidden !important;
            opacity: .01 !important;
          }

          [data-testid="stSidebar"] [role="radiogroup"] label {
            min-height: 2.6rem;
            padding: .56rem .7rem !important;
            border: 1px solid transparent;
            border-left: 3px solid transparent;
            border-radius: 7px;
            color: var(--risk-muted) !important;
            transition: background-color 180ms ease, border-color 180ms ease,
                        color 180ms ease, transform 180ms ease;
          }

          [data-testid="stSidebar"] [role="radiogroup"] label:hover {
            background: #151d26;
            color: #f3f7fb !important;
            transform: translateX(2px);
          }

          [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
            background: #18232d;
            border-color: #34424f;
            border-left-color: var(--risk-accent);
            color: #ffffff !important;
          }

          .risk-nav-label {
            margin: .35rem 0 .4rem;
            color: var(--risk-faint);
            font: 600 .56rem/1.3 "JetBrains Mono", Consolas, monospace;
            letter-spacing: .12em;
          }
          [data-testid="stSidebar"] .stButton button {
            min-height: 2.55rem;
            justify-content: flex-start;
            padding: .52rem .72rem;
            border: 0 !important;
            border-left: 2px solid transparent !important;
            border-radius: 0 !important;
            background: transparent !important;
            color: var(--risk-muted) !important;
            font: 600 .73rem/1.2 "JetBrains Mono", Consolas, monospace !important;
            letter-spacing: .035em;
            box-shadow: none !important;
          }
          [data-testid="stSidebar"] .stButton button:hover {
            border-left-color: rgba(191,230,255,.5) !important;
            background: rgba(191,230,255,.045) !important;
            color: #fff !important;
            transform: translateX(2px);
          }
          [data-testid="stSidebar"] .stButton button[kind="primary"] {
            border-left-color: var(--voice-model) !important;
            background: linear-gradient(90deg, rgba(91,124,255,.14), transparent) !important;
            color: #fff !important;
          }
          [data-testid="stSidebar"] [data-testid="baseButton-primary"] {
            border-left-color: var(--chapter-voice) !important;
            background: color-mix(in srgb, var(--chapter-voice) 10%, transparent) !important;
            color: #fff !important;
          }

          .risk-current-case {
            margin: .85rem 0 1rem;
            padding: .8rem .82rem .86rem;
            border-top: 1px solid color-mix(in srgb, var(--chapter-voice) 35%, transparent);
            border-bottom: 1px solid var(--risk-border-soft);
            background: color-mix(in srgb, var(--chapter-voice) 4%, transparent);
          }
          .risk-current-case > span { display:block; color:var(--risk-faint); font:600 .55rem/1.2 "JetBrains Mono",Consolas,monospace; letter-spacing:.1em; }
          .risk-current-case > strong { display:inline-block; margin:.4rem .55rem .28rem 0; color:#fff; font:400 1.25rem/1 "Instrument Serif",Georgia,serif; }
          .risk-current-case > b { font:600 .65rem/1 "JetBrains Mono",Consolas,monospace; letter-spacing:.04em; }
          .risk-current-case > small { display:block; color:var(--risk-muted); font-size:.72rem; }

          [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
            color: var(--risk-muted) !important;
          }

          .risk-sidebar-status {
            display: flex;
            align-items: center;
            gap: .55rem;
            margin: .7rem 0 1.1rem;
            padding: .62rem .72rem;
            border: 1px solid #3a2d36;
            border-radius: 8px;
            background: #171821;
            color: #e7c5c9;
            font-size: .78rem;
            font-weight: 650;
            letter-spacing: .02em;
          }

          .risk-status-dot {
            width: .52rem;
            height: .52rem;
            border-radius: 50%;
            background: var(--risk-critical);
            box-shadow: 0 0 0 4px rgba(196, 93, 84, .11);
          }

          h1, h2, h3 {
            color: #f4f7fb !important;
            letter-spacing: -.025em !important;
          }

          h1 {
            font-family: "Instrument Serif", Georgia, serif !important;
            font-size: clamp(2rem, 3vw, 3rem) !important;
            font-weight: 400 !important;
            line-height: 1.08 !important;
            margin-bottom: .55rem !important;
          }

          h2, h3 {
            font-weight: 690 !important;
          }

          p, label, [data-testid="stMarkdownContainer"],
          [data-testid="stCaptionContainer"] {
            color: var(--risk-text);
          }

          [data-testid="stCaptionContainer"] p,
          .stCaption, small {
            color: var(--risk-muted) !important;
            line-height: 1.55;
          }

          code, pre, [data-testid="stCodeBlock"], .risk-mono {
            font-family: "JetBrains Mono", "Cascadia Mono", Consolas, monospace !important;
            font-variant-ligatures: none;
          }

          div[data-testid="stMetric"] {
            min-height: 7.2rem;
            padding: 1rem 1.05rem !important;
            background: var(--risk-panel-raised) !important;
            border: 1px solid var(--risk-border) !important;
            border-left: 3px solid var(--risk-accent) !important;
            border-radius: 9px !important;
            box-shadow: 0 5px 18px rgba(0, 0, 0, .18);
            transition: transform 180ms ease, border-color 180ms ease, box-shadow 180ms ease;
          }

          div[data-testid="stMetric"]:hover {
            transform: translateY(-2px);
            border-color: #35516e !important;
            box-shadow: var(--risk-shadow);
          }

          [data-testid="stMetricLabel"] p {
            color: var(--risk-muted) !important;
            font-size: .74rem !important;
            font-weight: 650 !important;
            letter-spacing: .07em !important;
            text-transform: uppercase;
          }

          [data-testid="stMetricValue"] {
            color: #ffffff !important;
            font-family: "Instrument Serif", Georgia, serif !important;
            font-size: 1.65rem !important;
            font-weight: 400 !important;
            letter-spacing: -.025em;
            overflow-wrap: anywhere;
          }

          .risk-metric {
            --risk-card-accent: var(--risk-accent);
            position: relative;
            min-height: 7.35rem;
            height: 100%;
            padding: 1rem 1.05rem 1rem 1.15rem;
            overflow: hidden;
            border: 1px solid var(--risk-border);
            border-left: 3px solid var(--risk-card-accent);
            border-radius: 9px;
            background: var(--risk-panel-raised);
            box-shadow: 0 5px 18px rgba(0, 0, 0, .18);
            transition: transform 180ms ease, border-color 180ms ease, box-shadow 180ms ease;
            animation: risk-card-in 220ms ease-out both;
          }

          .risk-metric:hover {
            transform: translateY(-2px);
            border-color: #35516e;
            box-shadow: var(--risk-shadow);
          }

          .risk-metric.normal { --risk-card-accent: var(--risk-normal); }
          .risk-metric.warning { --risk-card-accent: var(--risk-warning); }
          .risk-metric.critical { --risk-card-accent: var(--risk-critical); }
          .risk-metric.synthetic { --risk-card-accent: var(--risk-synthetic); }
          .risk-metric.blocked {
            --risk-card-accent: var(--risk-blocked);
            background-color: #151923;
            background-image: repeating-linear-gradient(
              135deg,
              rgba(226, 85, 85, .045) 0,
              rgba(226, 85, 85, .045) 7px,
              transparent 7px,
              transparent 14px
            );
          }

          .risk-metric-label {
            color: var(--risk-muted);
            font-size: .7rem;
            font-weight: 680;
            letter-spacing: .075em;
            line-height: 1.3;
            text-transform: uppercase;
          }

          .risk-metric-value {
            margin-top: .52rem;
            color: #ffffff;
            font-family: "Instrument Serif", Georgia, serif;
            font-size: clamp(1.35rem, 2.1vw, 1.9rem);
            font-weight: 400;
            letter-spacing: -.03em;
            line-height: 1.15;
            overflow-wrap: anywhere;
          }

          .risk-metric-value.compact {
            font-size: 1.03rem;
            line-height: 1.28;
            letter-spacing: -.01em;
          }

          .risk-metric-value.mono {
            font-family: "JetBrains Mono", Consolas, "Liberation Mono", monospace;
            font-size: 1rem;
            letter-spacing: -.02em;
          }

          .risk-metric-value.counter {
            --risk-counter: var(--risk-target);
            counter-reset: metric-count var(--risk-counter);
            animation: risk-count-up 720ms cubic-bezier(.2, .7, .2, 1) both;
          }

          .risk-metric-value.counter span { display: none; }
          .risk-metric-value.counter::after { content: counter(metric-count); }

          [data-testid="stVerticalBlockBorderWrapper"] {
            border-color: var(--risk-border) !important;
            border-radius: 10px !important;
            background: rgba(13, 25, 39, .58);
          }

          [data-testid="stDataFrame"] {
            overflow: hidden;
            border: 1px solid var(--risk-border) !important;
            border-radius: 9px;
            background: var(--risk-panel) !important;
            box-shadow: 0 6px 22px rgba(0, 0, 0, .16);
            transition: border-color 180ms ease, box-shadow 180ms ease;
          }

          [data-testid="stDataFrame"]:hover {
            border-color: #36506a !important;
            box-shadow: var(--risk-shadow);
          }

          [data-testid="stDataFrame"] [role="columnheader"] {
            position: sticky !important;
            top: 0;
            z-index: 3;
            background: #152538 !important;
            color: #f3f7fb !important;
            font-weight: 690 !important;
          }

          [data-testid="stDataFrame"] [role="row"] {
            transition: background-color 160ms ease;
          }

          [data-testid="stDataFrame"] [role="row"]:hover {
            background: rgba(88, 166, 216, .08) !important;
          }

          [data-testid="stPlotlyChart"] {
            overflow: hidden;
            padding: .35rem;
            border: 1px solid var(--risk-border);
            border-radius: 10px;
            background: var(--risk-panel);
            box-shadow: 0 6px 22px rgba(0, 0, 0, .16);
            animation: risk-chart-in 260ms ease-out both;
          }

          [data-baseweb="select"] > div,
          [data-testid="stTextInputRootElement"],
          [data-testid="stTextArea"] textarea,
          [data-testid="stNumberInputContainer"] {
            background: #0e1b2a !important;
            border-color: var(--risk-border) !important;
            color: var(--risk-text) !important;
          }

          [data-baseweb="tab-list"] {
            gap: .35rem;
            border-bottom: 1px solid var(--risk-border);
          }

          [data-baseweb="tab"] {
            min-height: 2.75rem;
            padding: .65rem .95rem;
            border-radius: 7px 7px 0 0;
            color: var(--risk-muted) !important;
            transition: color 180ms ease, background-color 180ms ease;
          }

          [data-baseweb="tab"]:hover {
            color: #ffffff !important;
            background: #101f30 !important;
          }

          [aria-selected="true"][data-baseweb="tab"] {
            color: #ffffff !important;
            background: #13263a !important;
          }

          [data-testid="stAlert"] {
            border-radius: 8px !important;
            border-width: 1px !important;
            color: var(--risk-text) !important;
          }

          .stButton button,
          [data-testid="stFormSubmitButton"] button {
            border-color: #31516e !important;
            background: #10243a !important;
            color: #f6f9fc !important;
            font-weight: 680 !important;
            transition: transform 160ms ease, border-color 160ms ease, background-color 160ms ease;
          }

          .stButton button:hover,
          [data-testid="stFormSubmitButton"] button:hover {
            transform: translateY(-1px);
            border-color: var(--risk-accent) !important;
            background: #15304b !important;
          }

          .stButton button:focus-visible,
          [data-testid="stFormSubmitButton"] button:focus-visible,
          input:focus-visible,
          textarea:focus-visible,
          select:focus-visible,
          [role="radio"]:focus-visible,
          [role="tab"]:focus-visible,
          a:focus-visible {
            outline: 2px solid var(--chapter-voice, var(--risk-accent)) !important;
            outline-offset: 2px !important;
          }

          .control-page-head {
            position: relative;
            min-height: 8.1rem;
            margin: .1rem 0 1.45rem;
            padding: .85rem 9.5rem 1.05rem 0;
            border-bottom: 1px solid rgba(191, 230, 255, .13);
          }
          .control-page-head::before {
            content: "";
            position: absolute;
            right: 0;
            top: .55rem;
            width: 7.2rem;
            height: 7.2rem;
            border: 1px solid rgba(191, 230, 255, .13);
            border-radius: 50%;
            background:
              radial-gradient(circle at center, transparent 34%, color-mix(in srgb, var(--page-voice) 8%, transparent) 35%, transparent 37%),
              conic-gradient(from 118deg, transparent 0 12%, var(--page-voice) 12% 14%, transparent 14% 47%, color-mix(in srgb, var(--page-voice) 48%, transparent) 47% 48.5%, transparent 48.5% 82%, color-mix(in srgb, var(--page-voice) 28%, transparent) 82% 83%, transparent 83%);
            box-shadow: inset 0 0 30px rgba(91, 124, 255, .04), 0 0 45px rgba(91, 124, 255, .05);
            animation: chapter-orbit-settle 320ms var(--ease-authored) both;
          }
          .control-page-head::after {
            content: "EVIDENCE / CONTROL / TRACE";
            position: absolute;
            right: 1.15rem;
            top: 3.9rem;
            color: rgba(191,230,255,.45);
            font: 600 .5rem/1 "JetBrains Mono", Consolas, monospace;
            letter-spacing: .08em;
          }
          .control-page-head.voice-input { --page-voice: var(--voice-input); }
          .control-page-head.voice-drift { --page-voice: var(--voice-drift); }
          .control-page-head.voice-model { --page-voice: var(--voice-model); }
          .control-page-head.voice-outcome { --page-voice: var(--voice-outcome); }
          .control-page-head.voice-alert { --page-voice: var(--voice-alert); }
          .control-page-head.voice-control { --page-voice: var(--voice-lineage); }
          .control-page-head[class*="voice-"]::before {
            border-color: color-mix(in srgb, var(--page-voice) 26%, transparent);
            box-shadow: inset 0 0 30px color-mix(in srgb, var(--page-voice) 7%, transparent), 0 0 45px color-mix(in srgb, var(--page-voice) 6%, transparent);
          }
          .control-page-head[class*="voice-"] .control-chapter { color: var(--page-voice); }
          .control-page-head.voice-alert { min-height: 6.7rem; margin-bottom: .55rem; padding-top: .35rem; padding-bottom: .65rem; }
          .control-page-head.voice-alert h1 { font-size: clamp(2.5rem, 3.7vw, 4.15rem) !important; }

          .control-page-head h1 {
            margin: .18rem 0 .25rem !important;
            max-width: 18ch;
            font-size: clamp(2.55rem, 4.4vw, 4.95rem) !important;
            font-weight: 400 !important;
            line-height: .9 !important;
            letter-spacing: -.035em !important;
            text-transform: none;
            color: #f7f4ee !important;
            -webkit-text-fill-color: currentColor;
          }

          .control-chapter,
          .control-section-head span,
          .scenario-lab-title,
          .dossier-kicker {
            color: var(--voice-lineage);
            font-family: "JetBrains Mono", "Cascadia Mono", Consolas, monospace;
            font-size: .7rem;
            font-weight: 720;
            letter-spacing: .13em;
            text-transform: uppercase;
          }

          .control-subtitle {
            color: var(--risk-muted);
            font-size: .98rem;
            max-width: 64ch;
          }

          .control-section-head {
            position: relative;
            margin: 2.4rem 0 .9rem;
            padding-left: 1.1rem;
            border-left: 1px solid rgba(191,230,255,.28);
          }

          .control-section-head h3 {
            margin: .18rem 0 !important;
            font-family: "Inter", "Segoe UI", system-ui, sans-serif !important;
            font-size: 1.33rem !important;
            font-weight: 600 !important;
            letter-spacing: -.018em !important;
            text-transform: none;
          }

          .control-section-head p {
            margin: .2rem 0 0;
            color: var(--risk-muted);
            max-width: 76ch;
          }

          .control-health-hero {
            position: relative;
            display: flex;
            align-items: flex-end;
            justify-content: space-between;
            gap: 2rem;
            min-height: 11.5rem;
            margin: .75rem 0 1.25rem;
            padding: 1.5rem 1.7rem;
            overflow: hidden;
            border: 0;
            border-top: 1px solid rgba(191,230,255,.18);
            border-bottom: 1px solid rgba(191,230,255,.12);
            border-radius: 0;
            background: transparent;
          }

          .control-health-hero::after {
            content: "";
            position: absolute;
            width: 17rem;
            height: 17rem;
            right: -3rem;
            top: -4rem;
            border: 1px solid rgba(255, 91, 103, .16);
            border-radius: 47% 53% 58% 42%;
            box-shadow: 0 0 0 1.5rem rgba(255,91,103,.025), 0 0 0 3.2rem rgba(255,91,103,.018);
            transform: rotate(21deg);
            pointer-events: none;
          }

          .control-health-hero.critical { border-left-color: var(--risk-critical); }
          .control-health-hero.warning { border-left-color: var(--risk-warning); }
          .control-health-hero.normal { border-left-color: var(--risk-normal); }
          .control-health-hero.not_assessable { border-left-color: var(--risk-faint); }
          .control-health-hero span {
            display: block;
            margin-bottom: .5rem;
            color: var(--risk-muted);
            font-family: "JetBrains Mono", Consolas, monospace;
            font-size: .7rem;
            letter-spacing: .11em;
          }
          .control-health-hero strong {
            color: var(--risk-text);
            font-family: "Instrument Serif", Georgia, serif;
            font-size: clamp(2.8rem, 6vw, 5.2rem);
            font-weight: 400;
            letter-spacing: -.05em;
            line-height: .95;
          }
          .control-health-hero p {
            max-width: 36ch;
            margin: 0;
            color: var(--risk-muted);
            text-align: right;
          }

          .control-stat {
            min-height: 6.5rem;
            padding: .55rem .85rem .75rem;
            border-top: 2px solid var(--risk-border);
            background: transparent;
            transition: transform 220ms var(--ease-authored), border-color 220ms var(--ease-authored);
          }
          .control-stat:hover { transform: translateY(-3px); }
          .control-stat.warning { border-color: var(--risk-warning); }
          .control-stat.critical { border-color: var(--risk-critical); }
          .control-stat.blocked { border-color: var(--risk-blocked); }
          .control-stat.synthetic { border-color: var(--risk-synthetic); }
          .control-stat-label { color: var(--risk-muted); font-size: .68rem; letter-spacing: .08em; text-transform: uppercase; }
          .control-stat-value { color: var(--risk-text); font-family: "Instrument Serif", Georgia, serif; font-size: 2rem; font-weight: 400; font-variant-numeric: tabular-nums; }
          .control-stat-detail { color: var(--risk-faint); font-size: .75rem; }

          .scenario-lab-title {
            margin: 1rem 0 .42rem;
            color: var(--risk-muted);
            font-family: "Inter", "Segoe UI", system-ui, sans-serif;
            font-size: .78rem;
            font-weight: 600;
            letter-spacing: -.005em;
            text-transform: none;
          }
          [data-testid="stMain"] [role="radiogroup"] {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0;
            border-top: 1px solid var(--risk-border);
            border-bottom: 1px solid var(--risk-border);
          }
          [data-testid="stMain"] [role="radiogroup"] label {
            min-height: 5.25rem;
            padding: .72rem .75rem;
            border: 0;
            border-right: 1px solid var(--risk-border);
            border-radius: 0;
            background: transparent;
            color: var(--risk-muted) !important;
            white-space: pre-line;
            transition: color 220ms var(--ease-authored), background-color 220ms var(--ease-authored), transform 220ms var(--ease-authored);
          }
          [data-testid="stMain"] [role="radiogroup"] label:has(input:checked) {
            box-shadow: inset 0 -3px 0 var(--chapter-voice);
            background: color-mix(in srgb, var(--chapter-voice) 8%, transparent);
            color: var(--risk-text) !important;
          }
          [data-testid="stMain"] [role="radiogroup"] label:hover {
            background: rgba(255,255,255,.035);
            color: #fff !important;
            transform: translateY(-2px);
          }

          .signal-map-shell {
            min-height: 20rem;
            padding: .8rem 1rem .45rem;
            border: 1px solid rgba(191,230,255,.13);
            background: radial-gradient(circle at 48% 45%, rgba(91,124,255,.085), transparent 50%), rgba(7,11,16,.38);
            box-shadow: inset 0 1px rgba(255,255,255,.035), 0 28px 80px rgba(0,0,0,.18);
          }
          .signal-map-meta, .boundary-head, .boundary-axis {
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            color: var(--risk-faint);
            font: 600 .58rem/1.4 "JetBrains Mono", Consolas, monospace;
            letter-spacing: .09em;
          }
          .signal-map-meta b, .boundary-head b { color: var(--voice-lineage); font-weight: 600; }
          .signal-map { width: 100%; height: auto; overflow: visible; }
          .signal-thread { fill: none; stroke: var(--voice-lineage); stroke-width: 1.3; stroke-opacity: .30; stroke-dasharray: 3 5; }
          .signal-thread.secondary { stroke: var(--voice-alert); stroke-opacity: .52; }
          .signal-node .signal-halo { fill: transparent; stroke: currentColor; stroke-opacity: .18; stroke-width: 1; }
          .signal-node .signal-core { fill: currentColor; stroke: currentColor; stroke-width: 2; filter: drop-shadow(0 0 7px currentColor); }
          .signal-node { cursor: pointer; transition: color 220ms var(--ease-authored), transform 220ms var(--ease-authored); }
          .signal-node:hover .signal-halo { stroke-opacity: .55; }
          .signal-node:hover .signal-core { filter: drop-shadow(0 0 11px currentColor); }
          .signal-node.hollow .signal-core { fill: #090d12; filter: none; stroke-dasharray: 2 2; }
          .signal-node.mint { color: var(--voice-input); }
          .signal-node.violet { color: var(--voice-drift); }
          .signal-node.blue { color: var(--voice-model); }
          .signal-node.amber { color: var(--voice-outcome); }
          .signal-node.coral { color: var(--voice-alert); }
          .signal-node.not_assessable, .signal-node.not_assessable_for_alert_aggregation { color: #6f7883; }
          .signal-label { fill: currentColor; font: 600 8px/1 "Inter", "Segoe UI", sans-serif; letter-spacing: 1.2px; }
          .signal-state { fill: #aeb8c4; font: 600 6px/1 "Inter", "Segoe UI", sans-serif; letter-spacing: .4px; }
          .signal-footnote { fill: rgba(191,230,255,.42); font: 600 6px/1 "Inter", "Segoe UI", sans-serif; letter-spacing: 1px; }

          .decision-boundary {
            margin: 1rem 0 1.4rem;
            padding: .9rem 1rem .7rem;
            border-top: 1px solid rgba(91,124,255,.28);
            border-bottom: 1px solid rgba(91,124,255,.13);
            background: rgba(5,9,14,.35);
          }
          .boundary-track { position: relative; height: 2.8rem; margin: .85rem .1rem .2rem; }
          .boundary-track::before { content:""; position:absolute; left:0; right:0; top:1.25rem; height:3px; background: linear-gradient(90deg, rgba(75,214,162,.68) 0 8%, rgba(255,107,114,.55) 8% 100%); box-shadow: 0 0 14px rgba(191,230,255,.09); }
          .boundary-track > i { position:absolute; z-index:2; top:.84rem; width:11px; height:11px; margin-left:-5px; border:2px solid #090d12; border-radius:50%; background:#fff; box-shadow:0 0 0 3px rgba(91,124,255,.35), 0 0 14px rgba(91,124,255,.55); }
          .boundary-marker { position:absolute; top:-.1rem; transform:translateX(-.45rem); }
          .boundary-marker::after { content:""; position:absolute; top:1.25rem; left:.42rem; height:1.85rem; border-left:1px solid #fff; opacity:.55; }
          .boundary-marker em { display:block; color:#fff; font:600 .72rem/1 "JetBrains Mono",Consolas,monospace; font-style:normal; }
          .boundary-marker strong { position:absolute; top:2.7rem; left:0; color:var(--voice-lineage); font:600 .55rem/1 "JetBrains Mono",Consolas,monospace; letter-spacing:.06em; white-space:nowrap; }
          .boundary-axis { margin-top:.7rem; }

          .pagination-readout { color:var(--risk-muted); font-size:.78rem; }
          .pagination-readout strong { color:#fff; font-variant-numeric:tabular-nums; }
          .pagination-readout span { margin-left:.75rem; color:var(--voice-lineage); font:600 .6rem/1 "JetBrains Mono",Consolas,monospace; letter-spacing:.07em; }

          .workspace-switch [data-testid="stSegmentedControl"] { border-bottom:1px solid var(--risk-border); }

          [data-testid="stPlotlyChart"] {
            border-radius: 2px;
            border-color: rgba(191,230,255,.13);
            box-shadow: 0 20px 70px rgba(0,0,0,.20), inset 0 1px rgba(255,255,255,.025);
          }

          [data-testid="stDataFrame"] { border-radius: 2px; }

          @media (max-width: 1050px) {
            [data-testid="stMain"] [role="radiogroup"] { grid-template-columns: repeat(2, minmax(0, 1fr)); }
          }

          .model-passport { border-top: 1px solid var(--risk-border-soft); }
          .passport-row {
            padding: .48rem 0;
            border-bottom: 1px solid var(--risk-border-soft);
          }
          .passport-row span { display: block; color: var(--risk-faint); font-size: .6rem; letter-spacing: .08em; }
          .passport-row strong { display: block; color: var(--risk-text); font-family: "JetBrains Mono", Consolas, monospace; font-size: .72rem; overflow-wrap: anywhere; }

          .lifecycle-spine { margin: .5rem 0 1rem; padding: .25rem 0; }
          .lifecycle-node { position: relative; display: flex; gap: .85rem; min-height: 4.2rem; }
          .lifecycle-node:not(:last-child)::after { content: ""; position: absolute; left: .39rem; top: 1.15rem; bottom: -.1rem; border-left: 1px solid var(--risk-border); }
          .lifecycle-node i { z-index: 1; display: block; width: .8rem; height: .8rem; margin-top: .12rem; border: 2px solid var(--risk-faint); border-radius: 50%; background: var(--risk-bg); }
          .lifecycle-node.normal i, .lifecycle-node.authorized i { border-color: var(--risk-normal); background: var(--risk-normal); }
          .lifecycle-node.warning i { border-color: var(--risk-warning); background: var(--risk-warning); }
          .lifecycle-node.critical i { border-color: var(--risk-critical); background: var(--risk-critical); }
          .lifecycle-node.not_assessable i, .lifecycle-node.not_assessable_for_alert_aggregation i { background: var(--risk-bg); }
          .lifecycle-node span { display: block; color: var(--risk-muted); font-size: .66rem; letter-spacing: .08em; }
          .lifecycle-node strong { display: block; margin-top: .12rem; color: var(--risk-text); font-size: .9rem; }

          .control-inspection { border-top: 1px solid var(--risk-border); }
          .control-inspection-row, .dossier-row {
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            padding: .75rem .15rem;
            border-bottom: 1px solid var(--risk-border-soft);
          }
          .control-inspection-row span, .dossier-row span { color: var(--risk-muted); }
          .control-inspection-row strong, .dossier-row strong { color: var(--risk-text); font-family: "JetBrains Mono", Consolas, monospace; text-align: right; }
          .status-text.normal, .status-text.authorized { color: #91b89a; }
          .status-text.warning { color: #ddb06d; }
          .status-text.critical { color: #dc827a; }
          .status-text.blocked, .status-text.blocked_source_governance, .status-text.blocked_hard_gate { color: #c9808e; }

          .control-dossier {
            padding: 1rem 1.1rem;
            border: 1px solid var(--risk-border);
            border-left: 3px solid var(--risk-accent);
            border-radius: 6px;
            background: #10171f;
          }
          .control-dossier.critical { border-left-color: var(--risk-critical); }
          .control-dossier.warning { border-left-color: var(--risk-warning); }
          .control-dossier.synthetic { border-left-color: var(--risk-synthetic); }
          .control-dossier h3 { margin: .25rem 0 .75rem !important; font-size: 1.15rem !important; }
          .dossier-kicker {
            color: var(--chapter-voice);
            font-family: "Inter", "Segoe UI", system-ui, sans-serif;
            font-size: .72rem;
            font-weight: 600;
            letter-spacing: .01em;
            text-transform: none;
          }
          .control-dossier h3 { font-family: "Inter", "Segoe UI", system-ui, sans-serif !important; }

          .governed-unavailable {
            padding: 2.1rem 2.2rem;
            border: 1px solid var(--risk-border);
            border-radius: 6px;
            background: #10171f;
            text-align: center;
          }
          .unavailable-symbol { color: var(--risk-faint); font-size: 3.5rem; line-height: 1; }
          .governed-unavailable > span { color: var(--risk-faint); font-size: .68rem; letter-spacing: .1em; }
          .governed-unavailable h2 { margin: .4rem 0 !important; font-family: "Inter", "Segoe UI", system-ui, sans-serif; }
          .governed-unavailable p { max-width: 62ch; margin: 0 auto 1.5rem; color: var(--risk-muted); }
          .availability-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; text-align: left; }
          .availability-grid > div { padding: .85rem; border-top: 1px solid var(--risk-border); }
          .availability-grid strong { color: var(--risk-muted); font-size: .65rem; letter-spacing: .08em; }
          .availability-grid ul { margin: .55rem 0 0; padding: 0; list-style: none; color: var(--risk-text); }

          .synthetic-banner {
            margin: .5rem 0 1rem;
            padding: .8rem 1rem;
            border: 1px solid #474568;
            border-left: 3px solid var(--risk-synthetic);
            border-radius: 5px;
            background: #171725;
            color: #c9c6e5;
            font-family: "JetBrains Mono", Consolas, monospace;
            font-size: .78rem;
            letter-spacing: .04em;
          }

          .casebook-card {
            min-height: 10.5rem;
            padding: 1rem 1rem 1.15rem;
            border-top: 1px solid rgba(191,230,255,.20);
            border-bottom: 1px solid var(--risk-border-soft);
            background: linear-gradient(180deg, rgba(191,230,255,.025), transparent);
            transition: transform 180ms var(--ease-authored), border-color 180ms ease, background-color 180ms ease;
          }
          .casebook-card:hover { transform: translateY(-2px); border-top-color: var(--voice-lineage); }
          .casebook-card.active { border-top-color: var(--voice-alert); background: rgba(255,91,103,.045); }
          .casebook-card > span, .casebook-case-head > span, .casebook-narrative > span,
          .casebook-limitations > span, .evidence-chain-node > span {
            color: var(--voice-lineage);
            font: 600 .6rem/1.25 "JetBrains Mono",Consolas,monospace;
            letter-spacing: .1em;
          }
          .casebook-card h3 { margin: 1.2rem 0 .5rem !important; font: 400 1.28rem/1.03 "Instrument Serif",Georgia,serif !important; }
          .casebook-card p { min-height: 2.1rem; color: var(--risk-faint); font-size: .68rem; }
          .casebook-card strong { display:block; color:var(--risk-muted); font-size:.7rem; font-weight:500; }
          .casebook-case-head { margin: 2.6rem 0 1.2rem; padding: 1.1rem 0 1.4rem; border-top: 1px solid var(--risk-border); border-bottom: 1px solid var(--risk-border); }
          .casebook-case-title { max-width: 24ch; margin:.55rem 0 .4rem; color:var(--risk-text); font:400 clamp(2rem,4vw,3.4rem)/.96 "Instrument Serif",Georgia,serif; }
          .casebook-case-head p { margin:0; color:var(--risk-muted); font:500 .7rem/1.3 "JetBrains Mono",Consolas,monospace; }
          .casebook-narrative { margin: .6rem 0 1.25rem; padding: 1.1rem 1.2rem; border-left: 2px solid var(--risk-accent); background:#10171f; }
          .casebook-narrative.finding { border-left-color:var(--voice-lineage); }
          .casebook-narrative.observed { border-left-color:var(--voice-model); }
          .casebook-narrative.risk { border-left-color:var(--voice-outcome); }
          .casebook-narrative-title, .casebook-section-title { margin:.4rem 0 .5rem; color:var(--risk-text); font:500 1rem/1.25 "Inter","Segoe UI",sans-serif; }
          .casebook-narrative p { max-width:88ch; margin:0; color:#c6ccd3; line-height:1.65; }
          .casebook-evidence-chain { display:grid; grid-template-columns: repeat(11, auto); align-items:stretch; margin:.7rem 0 1rem; overflow-x:auto; border-top:1px solid var(--risk-border); border-bottom:1px solid var(--risk-border); }
          .evidence-chain-node { min-width:8.5rem; padding:1rem .8rem; background:#0d141c; }
          .evidence-chain-node strong { display:block; margin-top:.55rem; color:#f3f0ea; font:600 .72rem/1.35 "JetBrains Mono",Consolas,monospace; overflow-wrap:anywhere; }
          .evidence-chain-link { display:flex; align-items:center; justify-content:center; padding:0 .25rem; color:var(--voice-alert); font:400 1.2rem/1 "Instrument Serif",Georgia,serif; }
          .casebook-limitations { margin:1rem 0 1.25rem; padding:1rem 1.2rem; border:1px solid rgba(247,184,75,.24); background:rgba(247,184,75,.035); }
          .casebook-limitations > span { color:var(--voice-outcome); }
          .casebook-limitations ul { margin:.75rem 0 0; padding-left:1.1rem; color:#c8c2b7; }
          .casebook-limitations li { margin:.35rem 0; line-height:1.5; }
          .casebook-temporal-notice { margin:.75rem 0 1.35rem; padding:1rem 1.15rem; border:1px solid rgba(191,230,255,.28); border-left:3px solid var(--voice-lineage); background:rgba(191,230,255,.035); }
          .casebook-temporal-notice > span { display:block; margin-bottom:.75rem; color:var(--voice-lineage); font:600 .61rem/1.3 "JetBrains Mono",Consolas,monospace; letter-spacing:.09em; }
          .casebook-temporal-notice > div { display:grid; grid-template-columns:minmax(14rem,1fr) auto auto; gap:1rem; padding:.45rem 0; border-top:1px solid var(--risk-border-soft); align-items:center; }
          .casebook-temporal-notice code { color:#f2f0ea; font:.68rem/1.3 "JetBrains Mono",Consolas,monospace; }
          .casebook-temporal-notice div span { color:var(--risk-muted); font-size:.72rem; }
          .casebook-temporal-notice div strong { color:var(--voice-lineage); font-size:.72rem; }
          .casebook-temporal-notice p { margin:.75rem 0 0; color:var(--risk-muted); font-size:.76rem; }

          .control-footer {
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            margin-top: 3rem;
            padding-top: 1rem;
            border-top: 1px solid var(--risk-border-soft);
            color: var(--risk-faint);
            font-family: "JetBrains Mono", Consolas, monospace;
            font-size: .6rem;
            letter-spacing: .06em;
          }

          @media (max-width: 900px) {
            [data-testid="stMainBlockContainer"] { padding: 1.5rem 1.15rem 4rem; }
            .control-page-head { padding-right: 0; min-height: auto; }
            .control-page-head::before, .control-page-head::after { display: none; }
            .control-page-head h1 { font-size: clamp(2.7rem, 13vw, 4.6rem) !important; }
            .control-health-hero { align-items: flex-start; flex-direction: column; }
            .control-health-hero p { text-align: left; }
            .availability-grid { grid-template-columns: 1fr; }
            .control-footer { flex-direction: column; }
            .casebook-evidence-chain { grid-template-columns:1fr; }
            .evidence-chain-link { transform:rotate(90deg); min-height:1.6rem; }
            .casebook-temporal-notice > div { grid-template-columns:1fr; gap:.25rem; }
          }

          hr {
            border-color: var(--risk-border-soft) !important;
          }

          ::-webkit-scrollbar { width: 10px; height: 10px; }
          ::-webkit-scrollbar-track { background: #091522; }
          ::-webkit-scrollbar-thumb { background: #31445a; border-radius: 8px; }
          ::-webkit-scrollbar-thumb:hover { background: #405873; }

          @keyframes risk-card-in {
            from { transform: translateY(5px); }
            to { transform: translateY(0); }
          }

          @keyframes risk-chart-in {
            from { transform: translateY(4px); }
            to { transform: translateY(0); }
          }

          @keyframes risk-count-up {
            from { --risk-counter: 0; }
            to { --risk-counter: var(--risk-target); }
          }

          @keyframes chapter-orbit-settle {
            from { transform: rotate(-5deg); }
            to { transform: rotate(0); }
          }

          @media (prefers-reduced-motion: reduce) {
            *, *::before, *::after {
              animation-duration: .01ms !important;
              animation-iteration-count: 1 !important;
              transition-duration: .01ms !important;
            }
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _status_class(status: str | None) -> str:
    normalized = (status or "NEUTRAL").upper()
    if "BLOCKED" in normalized or "NOT_ASSESSABLE" in normalized or "NOT ASSESSABLE" in normalized:
        return "blocked"
    if "CRITICAL" in normalized:
        return "critical"
    if "SYNTHETIC" in normalized:
        return "synthetic"
    if "WARNING" in normalized:
        return "warning"
    if "NORMAL" in normalized or "AUTHORIZED" == normalized:
        return "normal"
    return "neutral"


def metric_card(label: str, value: Any, *, status: str | None = None, monospace: bool = False) -> None:
    rendered = str(value)
    classes = ["risk-metric-value"]
    if len(rendered) > 18:
        classes.append("compact")
    if monospace:
        classes.append("mono")
    target = ""
    first_render = not st.session_state.get("_risk_initial_motion_complete", False)
    if isinstance(value, Integral) and int(value) >= 0 and first_render:
        classes.append("counter")
        target = f' style="--risk-target: {int(value)}"'
    safe_label = html.escape(label)
    safe_value = html.escape(rendered)
    st.markdown(
        f"""
        <div class="risk-metric {_status_class(status)}">
          <div class="risk-metric-label">{safe_label}</div>
          <div class="{' '.join(classes)}"{target} aria-label="{safe_value}"><span>{safe_value}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _cell_style(value: Any) -> str:
    normalized = str(value).upper()
    if normalized in {"NORMAL", "AUTHORIZED"}:
        return "background-color: #1a2820; color: #9ac3a3; font-weight: 700"
    if normalized == "WARNING":
        return "background-color: #2d2518; color: #ddb06d; font-weight: 700"
    if normalized == "CRITICAL":
        return "background-color: #302021; color: #dc827a; font-weight: 700"
    if "BLOCKED" in normalized:
        return "background: repeating-linear-gradient(135deg,#2b2027 0,#2b2027 7px,#211c23 7px,#211c23 14px); color: #e39aa3; font-weight: 700"
    if normalized in {"NOT ASSESSABLE", "NOT_ASSESSABLE", "INSUFFICIENT_DATA"}:
        return "background-color: #222b36; color: #b9c3d0; font-weight: 650"
    return ""


def style_dataframe(frame: pd.DataFrame) -> pd.io.formats.style.Styler:
    styler = frame.style
    styler = styler.apply(
        lambda row: ["background-color: #151f2a" if row.name % 2 else "background-color: #111923"] * len(row),
        axis=1,
    )
    styler = styler.map(_cell_style)
    numeric = [column for column in frame.columns if pd.api.types.is_numeric_dtype(frame[column])]
    if numeric:
        styler = styler.set_properties(subset=numeric, **{"text-align": "right", "font-variant-numeric": "tabular-nums"})
    mono = [
        column for column in frame.columns
        if any(token in str(column).lower() for token in ("id", "sha", "hash", "metric", "entity", "feature"))
    ]
    if mono:
        styler = styler.set_properties(
            subset=mono,
            **{"font-family": '"JetBrains Mono","Cascadia Mono",Consolas,monospace', "font-size": "12px"},
        )
    return styler


def data_table(frame: pd.DataFrame, **kwargs: Any) -> None:
    st.dataframe(style_dataframe(frame), hide_index=True, width="stretch", **kwargs)


def style_plotly(figure: go.Figure) -> go.Figure:
    figure.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#111923",
        font={"color": "#E1DED7", "family": "Inter, Segoe UI, Arial, sans-serif", "size": 12},
        title={"font": {"color": "#F2F0EA", "size": 15}, "x": 0.01, "xanchor": "left"},
        margin={"l": 48, "r": 28, "t": 74, "b": 52},
        legend={
            "bgcolor": "rgba(13,19,26,.9)", "bordercolor": "#2A333E", "borderwidth": 1,
            "font": {"color": "#E1DED7"}, "title": {"font": {"color": "#9AA4B1"}},
        },
        hoverlabel={"bgcolor": "#18232D", "bordercolor": "#465563", "font": {"color": "#F2F0EA"}},
        transition={"duration": 180, "easing": "cubic-in-out"},
    )
    figure.update_xaxes(
        gridcolor="rgba(154,164,177,.10)", zerolinecolor="rgba(154,164,177,.18)",
        linecolor="#37424E", tickfont={"color": "#9AA4B1"}, title_font={"color": "#C9C6C0"},
    )
    figure.update_yaxes(
        gridcolor="rgba(154,164,177,.10)", zerolinecolor="rgba(154,164,177,.18)",
        linecolor="#37424E", tickfont={"color": "#9AA4B1"}, title_font={"color": "#C9C6C0"},
    )
    figure.update_traces(marker_line_color="rgba(255,255,255,.18)", marker_line_width=.6)
    return figure
