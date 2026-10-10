"""Dual light/dark glassmorphic theme.

Streamlit owns the active theme (both palettes are defined in .streamlit/config.toml; users pick Light, Dark or
System from the app menu). This module reads which one is active and injects matching CSS tokens, so the frosted
surfaces, glows and custom HTML follow the same theme as Streamlit's own widgets.
"""
from __future__ import annotations

from string import Template

import streamlit as st

TOKENS: dict[str, dict[str, str]] = {
    "dark": {
        "bg": "#05070C", "orbA": "rgba(45,212,191,0.24)", "orbB": "rgba(91,124,255,0.28)", "orbC": "rgba(245,181,68,0.11)",
        "glass": "rgba(255,255,255,0.055)", "glassStrong": "rgba(255,255,255,0.09)", "border": "rgba(255,255,255,0.13)",
        "text": "#F4F7FB", "muted": "#B3BDCB", "faint": "#8F9AAB", "accent": "#2DD4BF", "onAccent": "#03201C",
        "tint": "rgba(45,212,191,0.13)", "amber": "#F5C065", "amberTint": "rgba(245,192,101,0.14)",
        "blue": "#9DB6FF", "blueTint": "rgba(125,155,255,0.16)", "red": "#FF8A8A", "redTint": "rgba(255,120,120,0.14)",
        "violet": "#C4A8FF", "pink": "#FF9CCB", "line": "rgba(244,247,251,0.42)", "node": "rgba(255,255,255,0.07)",
        "shadow": "0 24px 70px rgba(0,0,0,0.45)", "nodeShadow": "0 8px 24px rgba(0,0,0,0.25)",
        "sidebar": "rgba(10,13,20,0.72)",
    },
    "light": {
        "bg": "#E9EFF6", "orbA": "rgba(20,184,166,0.28)", "orbB": "rgba(79,117,246,0.24)", "orbC": "rgba(245,158,11,0.18)",
        "glass": "rgba(255,255,255,0.58)", "glassStrong": "rgba(255,255,255,0.82)", "border": "rgba(255,255,255,0.95)",
        "text": "#08111F", "muted": "#3A4759", "faint": "#4E5B6E", "accent": "#0D6E66", "onAccent": "#FFFFFF",
        "tint": "rgba(13,110,102,0.11)", "amber": "#8A4B00", "amberTint": "rgba(245,158,11,0.18)",
        "blue": "#2346B8", "blueTint": "rgba(59,100,240,0.12)", "red": "#B42318", "redTint": "rgba(220,38,38,0.10)",
        "violet": "#6D28D9", "pink": "#BE185D", "line": "rgba(8,17,31,0.40)", "node": "rgba(255,255,255,0.85)",
        "shadow": "0 18px 50px rgba(15,23,42,0.10)", "nodeShadow": "0 6px 18px rgba(15,23,42,0.07)",
        "sidebar": "rgba(255,255,255,0.62)",
    },
}

CSS = Template("""
<style>
:root {
  --dr-bg: $bg; --dr-glass: $glass; --dr-glass-strong: $glassStrong; --dr-border: $border; --dr-text: $text;
  --dr-muted: $muted; --dr-faint: $faint; --dr-accent: $accent; --dr-on-accent: $onAccent; --dr-tint: $tint;
  --dr-amber: $amber; --dr-amber-tint: $amberTint; --dr-blue: $blue; --dr-blue-tint: $blueTint; --dr-red: $red;
  --dr-red-tint: $redTint; --dr-line: $line; --dr-node: $node; --dr-shadow: $shadow; --dr-node-shadow: $nodeShadow;
  --dr-brand: $accent; --dr-blur: blur(24px) saturate(150%);
  --dr-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
}

/* ---------- canvas: soft colour fields behind the frosted surfaces ---------- */
.stApp {
  background: radial-gradient(640px circle at 4% -6%, $orbA, transparent 62%),
              radial-gradient(760px circle at 104% 36%, $orbB, transparent 62%),
              radial-gradient(620px circle at 36% 110%, $orbC, transparent 60%), $bg !important;
  background-attachment: fixed !important;
}
[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1240px; }
h1, h2, h3 { letter-spacing: -0.02em; }
[data-testid="stCaptionContainer"], .dr-muted { color: var(--dr-muted); }
.dr-muted { font-size: .86rem; }

/* ---------- sidebar menu ---------- */
[data-testid="stSidebar"] { background: $sidebar; border-right: 1px solid var(--dr-border);
  backdrop-filter: var(--dr-blur); -webkit-backdrop-filter: var(--dr-blur); }
[data-testid="stSidebar"] > div:first-child { background: transparent; }
[data-testid="stSidebarNavLink"] { border-radius: 11px; min-height: 2.5rem; }
[data-testid="stSidebarNavLink"][aria-current="page"] { background: var(--dr-tint); }
[data-testid="stSidebarNavLink"][aria-current="page"] span { font-weight: 600; }
[data-testid="stNavSectionHeader"] { font-family: var(--dr-mono); font-size: 10.5px !important; letter-spacing: .12em;
  text-transform: uppercase; color: var(--dr-faint); }
[data-testid="stLogo"] { border-radius: 12px; height: 2.75rem; }

/* ---------- glass surfaces ---------- */
[class*="st-key-glass"], [data-testid="stForm"], [data-testid="stMetric"] {
  background: var(--dr-glass); border: 1px solid var(--dr-border) !important; box-shadow: var(--dr-shadow);
  backdrop-filter: var(--dr-blur); -webkit-backdrop-filter: var(--dr-blur);
}
[class*="st-key-glass"] { border-radius: 24px; padding: 1.6rem 1.7rem; }
[data-testid="stForm"] { border-radius: 20px; padding: 1.3rem 1.4rem; }
[data-testid="stMetric"] { border-radius: 16px; padding: .85rem 1rem; box-shadow: var(--dr-node-shadow); }
[class*="st-key-glass"] [data-testid="stForm"] { background: transparent; border: 0 !important; box-shadow: none;
  padding: 0; backdrop-filter: none; -webkit-backdrop-filter: none; }
[data-testid="stExpander"] details { background: var(--dr-glass); border: 1px solid var(--dr-border) !important;
  border-radius: 16px; backdrop-filter: var(--dr-blur); -webkit-backdrop-filter: var(--dr-blur); }
[data-testid="stVerticalBlockBorderWrapper"], div[data-testid="stVerticalBlock"][class*="st-key-"]:not([class*="st-key-glass"]) {
  border-radius: 18px; }
[data-testid="stAlert"] { border-radius: 14px; border: 1px solid var(--dr-border);
  backdrop-filter: var(--dr-blur); -webkit-backdrop-filter: var(--dr-blur); }
[data-testid="stDataFrame"], [data-testid="stTable"] { border-radius: 14px; overflow: hidden; }
[data-testid="stPopoverBody"] { border-radius: 16px; }

/* ---------- controls ---------- */
.stButton button, .stFormSubmitButton button, .stDownloadButton button, .stLinkButton a {
  border-radius: 12px; font-weight: 500; min-height: 2.75rem; }
[data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"] {
  background: var(--dr-glass-strong); border: 1px solid var(--dr-border); }
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {
  background: var(--dr-accent) !important; border-color: var(--dr-accent) !important; color: var(--dr-on-accent) !important;
  font-weight: 600; }
[data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseButton-primaryFormSubmit"]:hover { filter: brightness(1.07); }
[data-testid="stBaseButton-primary"] p, [data-testid="stBaseButton-primaryFormSubmit"] p { color: var(--dr-on-accent); }
[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div, [data-baseweb="base-input"] {
  border-radius: 12px !important; }
[data-testid="stPageLink"] a { border-radius: 12px; }
[data-testid="stMetricLabel"] p { font-family: var(--dr-mono); font-size: 11px !important; letter-spacing: .08em;
  text-transform: uppercase; color: var(--dr-faint); }
[data-testid="stMetricValue"] { letter-spacing: -0.02em; }
hr { border-color: var(--dr-border) !important; }

/* ---------- page header ---------- */
.dr-header { padding-bottom: 1rem; margin-bottom: 1.4rem; border-bottom: 1px solid var(--dr-border); }
.dr-eyebrow, .dr-kicker { font-family: var(--dr-mono); font-size: 11.5px; letter-spacing: .14em; text-transform: uppercase;
  color: var(--dr-accent); }
.dr-eyebrow { margin-bottom: .55rem; }
.dr-header h1 { font-size: 2.3rem; font-weight: 600; line-height: 1.08; letter-spacing: -0.03em; margin: 0; padding: 0; }
.dr-header p { margin: .55rem 0 0 0; color: var(--dr-muted); font-size: 1.02rem; max-width: 760px; line-height: 1.5; }

/* ---------- badges ---------- */
.dr-badge { display: inline-block; padding: 3px 8px; border-radius: 999px; font-family: var(--dr-mono); font-size: 10.5px;
  font-weight: 500; letter-spacing: .06em; text-transform: uppercase; margin-right: .3rem; vertical-align: middle;
  background: color-mix(in srgb, currentColor 12%, transparent); }
.dr-demo { color: var(--dr-amber); } .dr-live { color: var(--dr-accent); } .dr-cache { color: var(--dr-blue); }
.dr-upload { color: $violet; } .dr-observed { color: var(--dr-accent); } .dr-inferred { color: var(--dr-blue); }
.dr-speculative { color: $pink; } .dr-flag { color: var(--dr-red); }
.dr-pill { display: inline-block; font-family: var(--dr-mono); font-size: 11px; letter-spacing: .08em; padding: 4px 9px;
  border-radius: 999px; text-transform: uppercase; white-space: nowrap; }
.dr-pill.completed { background: var(--dr-tint); color: var(--dr-accent); }
.dr-pill.running { background: var(--dr-blue-tint); color: var(--dr-blue); }
.dr-pill.failed { background: var(--dr-red-tint); color: var(--dr-red); }
.dr-pill.demo { background: var(--dr-amber-tint); color: var(--dr-amber); }
.dr-pill.live { background: var(--dr-glass-strong); color: var(--dr-muted); }
.dr-step { font-family: var(--dr-mono); font-size: 11px; color: var(--dr-accent); letter-spacing: .06em; }

/* ---------- account chip (sidebar) ---------- */
.dr-user { display: flex; align-items: center; gap: .75rem; padding: .25rem .1rem .6rem; }
.dr-avatar { width: 38px; height: 38px; flex: none; border-radius: 50%; display: flex; align-items: center;
  justify-content: center; font-weight: 600; background: var(--dr-tint); color: var(--dr-accent);
  border: 1px solid var(--dr-border); }
.dr-user b { display: block; font-size: .92rem; } .dr-user span { font-size: .78rem; color: var(--dr-faint); }

/* ---------- landing ---------- */
.dr-display { font-size: 3rem; line-height: 1.04; font-weight: 600; letter-spacing: -0.035em; margin: .7rem 0 .9rem;
  text-wrap: balance; }
.dr-lead { font-size: 1.06rem; line-height: 1.6; color: var(--dr-muted); margin: 0 0 1.1rem; text-wrap: pretty; }
.dr-greeting h2 { font-size: 1.75rem; font-weight: 600; margin: .15rem 0 0; padding: 0; }
.dr-chips { display: flex; flex-wrap: wrap; gap: .5rem; margin: .4rem 0 .2rem; }
.dr-chip { font-family: var(--dr-mono); font-size: 11px; letter-spacing: .06em; padding: 5px 10px; border-radius: 999px;
  background: var(--dr-glass-strong); color: var(--dr-muted); border: 1px solid var(--dr-border); }
.dr-figure { position: relative; padding: 8px; border-radius: 24px; background: var(--dr-glass-strong);
  border: 1px solid var(--dr-border); }
.dr-figure img { display: block; width: 100%; aspect-ratio: 4 / 3; object-fit: cover; object-position: 55% 35%;
  border-radius: 18px; }
.dr-figure .dr-tag { position: absolute; left: 22px; bottom: 22px; display: flex; align-items: center; gap: 8px;
  padding: 8px 12px; border-radius: 999px; font-family: var(--dr-mono); font-size: 11px; letter-spacing: .1em;
  color: #F4F7FB; background: rgba(5,7,12,.55); border: 1px solid rgba(255,255,255,.18);
  backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px); }
.dr-dot-live { width: 8px; height: 8px; border-radius: 50%; background: #2DD4BF; }
.dr-section-title { font-size: 1.35rem; font-weight: 600; margin: 0; padding: 0; letter-spacing: -0.01em; }
.dr-section-lead { margin: .35rem 0 1rem; color: var(--dr-muted); font-size: .95rem; max-width: 700px; line-height: 1.5; }

/* workflow graph */
.dr-flow-wide { display: block; width: 100%; overflow-x: auto; }
.dr-flow-wide svg { display: block; width: 100%; min-width: 640px; height: auto; }
.dr-flow-steps { display: none; list-style: none; margin: 0; padding: 0; }
.dr-flow-steps li { display: flex; flex-direction: column; }
.dr-flow-steps .dr-node { display: flex; align-items: center; gap: 12px; padding: 10px 12px; border-radius: 12px;
  background: var(--dr-node); border: 1px solid var(--dr-border); font-weight: 600; font-size: .92rem; }
.dr-flow-steps .dr-node.decide { background: var(--dr-tint); border-color: var(--dr-accent); }
.dr-flow-steps .dr-node small { font-family: var(--dr-mono); font-size: 11px; font-weight: 500; color: var(--dr-faint); }
.dr-flow-steps .dr-node em { margin-left: auto; font-style: normal; font-family: var(--dr-mono); font-size: 10px;
  letter-spacing: .08em; color: var(--dr-accent); }
.dr-flow-steps .dr-link { margin-left: 22px; width: 2px; height: 14px; background: var(--dr-line); }
.dr-flow-note { margin-top: .8rem; padding: 10px 12px; border-radius: 12px; font-size: .85rem; line-height: 1.5;
  color: var(--dr-muted); border: 1px dashed var(--dr-accent); display: none; }
.dr-legend { display: flex; flex-wrap: wrap; gap: 1.2rem; margin-top: .9rem; font-size: .84rem; color: var(--dr-muted); }
.dr-legend span { display: flex; align-items: center; gap: .5rem; }
.dr-legend i { display: inline-block; width: 24px; height: 0; }

/* agent team cards */
.dr-agents { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(220px, 100%), 1fr)); gap: 16px; }
.dr-agent { box-sizing: border-box; padding: 18px; border-radius: 18px; display: flex; flex-direction: column; gap: 10px;
  background: var(--dr-glass); border: 1px solid var(--dr-border); box-shadow: var(--dr-node-shadow);
  backdrop-filter: var(--dr-blur); -webkit-backdrop-filter: var(--dr-blur); }
.dr-agent header { display: flex; align-items: center; justify-content: space-between; }
.dr-agent .dr-icon { width: 40px; height: 40px; border-radius: 12px; display: flex; align-items: center;
  justify-content: center; background: var(--dr-tint); color: var(--dr-accent); }
.dr-agent header small { font-family: var(--dr-mono); font-size: 12px; color: var(--dr-faint); }
.dr-agent h4 { margin: 0; padding: 0; font-size: .98rem; font-weight: 600; }
.dr-agent p { margin: 0; flex: 1; font-size: .84rem; line-height: 1.5; color: var(--dr-muted); }
.dr-agent .dr-pill { align-self: flex-start; font-size: 10px; }
.dr-agent .dr-pill.llm { background: var(--dr-tint); color: var(--dr-accent); }
.dr-agent .dr-pill.rules { background: var(--dr-glass-strong); color: var(--dr-muted); }

/* recent runs */
.dr-run-q { font-size: .98rem; font-weight: 500; line-height: 1.4; margin: 0; }
.dr-run-meta { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; justify-content: flex-end; }

/* ---------- login ---------- */
.dr-auth-title { font-size: 1.55rem; font-weight: 600; margin: 0; padding: 0; letter-spacing: -0.01em; }
.dr-auth-sub { margin: .3rem 0 1rem; color: var(--dr-muted); font-size: .92rem; }
.dr-or { display: flex; align-items: center; gap: 12px; margin: .9rem 0 .4rem; font-family: var(--dr-mono); font-size: 11px;
  letter-spacing: .08em; color: var(--dr-faint); }
.dr-or::before, .dr-or::after { content: ""; flex: 1; height: 1px; background: var(--dr-border); }
.dr-fineprint { font-size: .78rem; color: var(--dr-faint); text-align: center; margin: .8rem 0 0; line-height: 1.5; }
.st-key-glass_auth .stFormSubmitButton button, .st-key-glass_auth .stButton button { width: 100%; }
.st-key-sso_google button::before, .st-key-sso_microsoft button::before { content: ""; width: 18px; height: 18px;
  margin-right: 10px; background-repeat: no-repeat; background-position: center; background-size: contain; }
.st-key-sso_google button::before { background-image: url("$googleIcon"); }
.st-key-sso_microsoft button::before { background-image: url("$microsoftIcon"); width: 16px; height: 16px; }
.dr-login-figure { padding: 8px; border-radius: 26px; background: var(--dr-glass); border: 1px solid var(--dr-border);
  box-shadow: var(--dr-shadow); backdrop-filter: var(--dr-blur); -webkit-backdrop-filter: var(--dr-blur); }
.dr-login-figure img { display: block; width: 100%; aspect-ratio: 16 / 10; object-fit: cover; object-position: 50% 30%;
  border-radius: 19px; }
.dr-login-copy h1 { font-size: 2.5rem; line-height: 1.08; font-weight: 600; letter-spacing: -0.03em; margin: .6rem 0;
  padding: 0; text-wrap: balance; }
.dr-login-copy p { color: var(--dr-muted); font-size: 1rem; line-height: 1.55; max-width: 440px; margin: 0; }

/* ---------- responsive: tablet and phone ---------- */
@media (max-width: 1024px) {
  .block-container { padding-left: 1.4rem; padding-right: 1.4rem; }
  .dr-display { font-size: 2.4rem; }
}
@media (max-width: 720px) {
  .block-container { padding: 1.2rem .9rem 2.5rem; }
  [class*="st-key-glass"] { padding: 1.1rem; border-radius: 20px; }
  .dr-display { font-size: 2rem; }
  .dr-header h1, .dr-login-copy h1 { font-size: 1.8rem; }
  .dr-flow-wide, .dr-legend { display: none; }
  .dr-flow-steps, .dr-flow-note { display: flex; flex-direction: column; }
  .dr-flow-note { display: block; }
  .dr-run-meta { justify-content: flex-start; }
}
</style>
""")

GOOGLE_ICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 '
               '9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 '
               '9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 '
               '7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-'
               '4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/><path '
               'fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-'
               '4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>')
MICROSOFT_ICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 22 22"><rect width="10" height="10" fill="#F25022"/>'
                  '<rect x="12" width="10" height="10" fill="#7FBA00"/><rect y="12" width="10" height="10" fill="#00A4EF"/>'
                  '<rect x="12" y="12" width="10" height="10" fill="#FFB900"/></svg>')


def _svg_uri(svg: str) -> str:
    from urllib.parse import quote

    return "data:image/svg+xml;charset=utf-8," + quote(svg)


def active_theme() -> str:
    """'light' or 'dark', as currently shown by Streamlit (falls back to light on older versions)."""
    try:
        kind = st.context.theme.type
    except Exception:  # st.context.theme is unavailable outside a session or on older Streamlit
        kind = None
    return kind if kind in TOKENS else "light"


def tokens() -> dict[str, str]:
    return TOKENS[active_theme()]


def inject_theme() -> None:
    values = dict(tokens(), googleIcon=_svg_uri(GOOGLE_ICON), microsoftIcon=_svg_uri(MICROSOFT_ICON))
    st.markdown(CSS.substitute(values), unsafe_allow_html=True)


def hide_sidebar() -> None:
    st.markdown("<style>[data-testid='stSidebar'], [data-testid='stSidebarCollapsedControl'], "
                "[data-testid='stExpandSidebarButton'] { display: none !important; }</style>", unsafe_allow_html=True)
