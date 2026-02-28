"""
VendorGuard AI — Streamlit Dashboard
Enterprise Vendor Risk Intelligence powered by Azure OpenAI GPT-4o
"""

import json
import os
from datetime import datetime

import plotly.graph_objects as go
import streamlit as st

from agents.research_agent import run_vendor_analysis

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="VendorGuard AI",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Dark theme CSS ────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    .stApp, [data-testid="stAppViewContainer"] {
        background-color: #0d1117;
        color: #e6edf3;
    }
    [data-testid="stSidebar"] {
        background-color: #161b22;
        border-right: 1px solid #30363d;
    }
    [data-testid="stSidebar"] * { color: #c9d1d9 !important; }

    .vg-header { font-size: 2.4rem; font-weight: 800; color: #58a6ff; }
    .vg-sub    { font-size: 0.95rem; color: #8b949e; margin-bottom: 1rem; }

    .score-card {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 10px;
        padding: 1rem;
    }
    .score-dim-label {
        font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.08em; color: #8b949e;
    }
    .score-num { font-size: 2.2rem; font-weight: 800; line-height: 1; }
    .score-tag { font-size: 0.75rem; color: #8b949e; }
    .score-summary { font-size: 0.82rem; color: #c9d1d9; margin-top: 0.4rem; line-height: 1.4; }

    .rai-box {
        background: #1c2128; border: 1px solid #d29922; border-radius: 8px;
        padding: 0.9rem 1.1rem; font-size: 0.82rem; color: #d29922; margin-top: 1rem;
    }
    .section-title {
        font-size: 1rem; font-weight: 700; color: #58a6ff;
        margin: 1rem 0 0.4rem; border-bottom: 1px solid #21262d; padding-bottom: 0.3rem;
    }
    .finding-item {
        font-size: 0.85rem; color: #c9d1d9; padding: 0.2rem 0;
        border-bottom: 1px solid #21262d;
    }
    div[data-testid="stTextInput"] input {
        background: #161b22 !important; color: #e6edf3 !important;
        border: 1px solid #30363d !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Session state ─────────────────────────────────────────────────────────────
if "history" not in st.session_state:
    st.session_state.history = []
if "current_result" not in st.session_state:
    st.session_state.current_result = None
if "vendor_input" not in st.session_state:
    st.session_state.vendor_input = ""

# ── Helpers ───────────────────────────────────────────────────────────────────

SCORE_THRESHOLDS = (3.5, 6.5)


def _color(score: float) -> str:
    if score <= SCORE_THRESHOLDS[0]:
        return "#2ecc71"
    if score <= SCORE_THRESHOLDS[1]:
        return "#f39c12"
    return "#e74c3c"


def _label(score: float) -> str:
    if score <= SCORE_THRESHOLDS[0]:
        return "Low Risk"
    if score <= SCORE_THRESHOLDS[1]:
        return "Moderate Risk"
    return "High Risk"


def _rec_icon(rec: str) -> str:
    return {"APPROVE": "✅", "REJECT": "❌", "FLAG FOR HUMAN REVIEW": "⚠️"}.get(rec, "")


def _save_audit(result: dict) -> None:
    try:
        os.makedirs("data", exist_ok=True)
        log_path = "data/audit_log.json"
        logs = []
        if os.path.exists(log_path):
            with open(log_path) as f:
                logs = json.load(f)
        logs.append({
            "timestamp": result.get("timestamp"),
            "vendor": result.get("vendor_name"),
            "weighted_score": result.get("weighted_score"),
            "recommendation": result.get("recommendation"),
            "confidence": result.get("confidence_level"),
        })
        with open(log_path, "w") as f:
            json.dump(logs, f, indent=2)
    except Exception:
        pass


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🛡️ VendorGuard AI")
    st.caption("Enterprise Vendor Risk Intelligence")
    st.divider()

    st.markdown("### Quick Demo")
    st.caption("Pre-loaded scenarios:")
    if st.button("⚡ SolarWinds — High Risk", use_container_width=True):
        st.session_state.vendor_input = "SolarWinds"
        st.rerun()
    if st.button("✅ Johnson & Johnson — Low Risk", use_container_width=True):
        st.session_state.vendor_input = "Johnson & Johnson"
        st.rerun()
    if st.button("🔍 Frontier Communications", use_container_width=True):
        st.session_state.vendor_input = "Frontier Communications"
        st.rerun()

    st.divider()
    st.markdown("### Scoring Guide")
    st.success("1.0 – 3.5  →  ✅ APPROVE")
    st.warning("3.6 – 6.5  →  ⚠️ FLAG FOR REVIEW")
    st.error("6.6 – 10.0  →  ❌ REJECT")

    if st.session_state.history:
        st.divider()
        st.markdown("### Recent Reports")
        for i, item in enumerate(reversed(st.session_state.history[-5:])):
            sc = item.get("weighted_score", 0)
            icon = _rec_icon(item.get("recommendation", ""))
            if st.button(
                f"{icon} {item['vendor_name']} ({sc:.1f})",
                use_container_width=True,
                key=f"hist_{i}",
            ):
                st.session_state.current_result = item
                st.rerun()

        st.divider()
        total    = len(st.session_state.history)
        approved = sum(1 for r in st.session_state.history if r.get("recommendation") == "APPROVE")
        flagged  = sum(1 for r in st.session_state.history if r.get("recommendation") == "FLAG FOR HUMAN REVIEW")
        rejected = sum(1 for r in st.session_state.history if r.get("recommendation") == "REJECT")
        st.metric("Total Analyzed", total)
        ca, cf, cr = st.columns(3)
        ca.metric("✅", approved)
        cf.metric("⚠️", flagged)
        cr.metric("❌", rejected)

# ── Main panel ────────────────────────────────────────────────────────────────
st.markdown('<div class="vg-header">🛡️ VendorGuard AI</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="vg-sub">Enterprise Vendor Risk Intelligence · '
    'Powered by Azure OpenAI GPT-4o · Responsible AI Enabled</div>',
    unsafe_allow_html=True,
)
st.divider()

col_input, col_btn = st.columns([5, 1])
with col_input:
    vendor_name = st.text_input(
        "Vendor",
        value=st.session_state.vendor_input,
        placeholder="Enter vendor name (e.g. SolarWinds, Accenture, Frontier…)",
        label_visibility="collapsed",
    )
with col_btn:
    analyze = st.button("🔍 Analyze", type="primary", use_container_width=True)

# ── Run analysis ──────────────────────────────────────────────────────────────
if analyze:
    name = vendor_name.strip()
    if name:
        st.session_state.vendor_input = ""
        with st.spinner(f"Analyzing **{name}** across 4 risk dimensions…"):
            result = run_vendor_analysis(name)
            result["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            st.session_state.current_result = result
            st.session_state.history.append(result)
            _save_audit(result)
    else:
        st.warning("Please enter a vendor name.")

# ── Display report ────────────────────────────────────────────────────────────
r = st.session_state.current_result

if r is None and st.session_state.history:
    r = st.session_state.history[0]
    st.caption("Showing most recent report. Enter a vendor name to run a new analysis.")

if r:
    score = float(r.get("weighted_score", 5.0))
    rec   = r.get("recommendation", "FLAG FOR HUMAN REVIEW")
    conf  = r.get("confidence_level", "N/A")
    icon  = _rec_icon(rec)
    clr   = _color(score)

    st.divider()

    # Recommendation banner
    banner = f"{icon}  **{rec}**  —  Risk Score: **{score:.1f}/10**  ·  Confidence: **{conf}**"
    if rec == "APPROVE":
        st.success(banner)
    elif rec == "REJECT":
        st.error(banner)
    else:
        st.warning(banner)

    # ── Charts ────────────────────────────────────────────────────────────────
    fin_s = r.get("financial_risk",  {}).get("score", 5)
    sec_s = r.get("security_risk",   {}).get("score", 5)
    com_s = r.get("compliance_risk", {}).get("score", 5)
    rep_s = r.get("reputation_risk", {}).get("score", 5)
    dims       = ["Financial", "Security", "Compliance", "Reputation"]
    raw_scores = [fin_s, sec_s, com_s, rep_s]

    c1, c2, c3 = st.columns([1, 1.5, 1.5])

    with c1:
        st.subheader("Overall Score")
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=score,
            number={"suffix": "/10", "font": {"size": 30, "color": clr}},
            gauge={
                "axis": {"range": [0, 10], "tickcolor": "#8b949e"},
                "bar": {"color": clr, "thickness": 0.25},
                "bgcolor": "#161b22",
                "bordercolor": "#30363d",
                "steps": [
                    {"range": [0,   3.5], "color": "#1a4731"},
                    {"range": [3.5, 6.5], "color": "#3d2b00"},
                    {"range": [6.5, 10],  "color": "#3d1212"},
                ],
                "threshold": {
                    "line": {"color": clr, "width": 3},
                    "thickness": 0.75,
                    "value": score,
                },
            },
        ))
        fig_gauge.update_layout(
            height=240,
            margin=dict(t=20, b=0, l=20, r=20),
            paper_bgcolor="#0d1117",
            font_color="#e6edf3",
        )
        st.plotly_chart(fig_gauge, use_container_width=True)
        st.markdown(
            f"<div style='text-align:center;font-size:0.9rem;color:{clr};font-weight:700;'>"
            f"{_label(score)}</div>",
            unsafe_allow_html=True,
        )

    with c2:
        st.subheader("Risk Profile")
        fig_radar = go.Figure(go.Scatterpolar(
            r=raw_scores + [raw_scores[0]],
            theta=dims + [dims[0]],
            fill="toself",
            fillcolor="rgba(231,76,60,0.18)",
            line=dict(color="#e74c3c", width=2),
            marker=dict(size=6, color="#e74c3c"),
        ))
        fig_radar.update_layout(
            polar=dict(
                bgcolor="#161b22",
                radialaxis=dict(range=[0, 10], visible=True, color="#8b949e", gridcolor="#30363d"),
                angularaxis=dict(color="#8b949e", gridcolor="#30363d"),
            ),
            height=240,
            margin=dict(t=20, b=0, l=40, r=40),
            showlegend=False,
            paper_bgcolor="#0d1117",
            font_color="#c9d1d9",
        )
        st.plotly_chart(fig_radar, use_container_width=True)

    with c3:
        st.subheader("Breakdown")
        weights    = ["25%", "35%", "25%", "15%"]
        bar_colors = [_color(s) for s in raw_scores]
        fig_bar = go.Figure(go.Bar(
            x=raw_scores,
            y=[f"{d}  ({w})" for d, w in zip(dims, weights)],
            orientation="h",
            marker_color=bar_colors,
            text=[f"{s}/10" for s in raw_scores],
            textposition="outside",
            textfont=dict(color="#e6edf3"),
        ))
        fig_bar.update_layout(
            xaxis=dict(range=[0, 12], color="#8b949e", gridcolor="#30363d"),
            yaxis=dict(color="#c9d1d9"),
            height=240,
            margin=dict(t=20, b=0, l=10, r=60),
            showlegend=False,
            paper_bgcolor="#0d1117",
            plot_bgcolor="#0d1117",
            font_color="#c9d1d9",
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    st.markdown("")

    # ── Executive Summary ─────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Executive Summary</div>', unsafe_allow_html=True)
    st.info(r.get("executive_summary", ""))

    # ── 4 Score Cards ─────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Detailed Risk Analysis</div>', unsafe_allow_html=True)
    dim_meta = [
        ("💰 Financial Risk",  "financial_risk",  "25% weight"),
        ("🔒 Security Risk",   "security_risk",   "35% weight"),
        ("📋 Compliance Risk", "compliance_risk",  "25% weight"),
        ("📰 Reputation Risk", "reputation_risk",  "15% weight"),
    ]
    cols = st.columns(4)
    for col, (label, key, weight) in zip(cols, dim_meta):
        data  = r.get(key, {})
        sv    = data.get("score", 5)
        color = _color(sv)
        with col:
            st.markdown(
                f"""
                <div class="score-card">
                    <div class="score-dim-label">{label} · {weight}</div>
                    <div class="score-num" style="color:{color};">{sv}
                        <span style="font-size:1rem;color:#8b949e;">/10</span>
                    </div>
                    <div class="score-tag" style="color:{color};">{_label(float(sv))}</div>
                    <div class="score-summary">{data.get('explanation', '')}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown("")

    # Key facts expanders
    for label, key, _ in dim_meta:
        data  = r.get(key, {})
        facts = data.get("key_facts", [])
        if facts:
            with st.expander(f"{label} — Key Facts"):
                for fact in facts:
                    st.markdown(
                        f'<div class="finding-item">• {fact}</div>',
                        unsafe_allow_html=True,
                    )

    # ── Recommendation reasoning ───────────────────────────────────────────────
    st.markdown('<div class="section-title">Why This Recommendation</div>', unsafe_allow_html=True)
    st.markdown(f"> {r.get('recommendation_reason', '')}")

    if r.get("confidence_reason"):
        st.caption(f"**Confidence ({conf}):** {r['confidence_reason']}")

    # ── Next steps ────────────────────────────────────────────────────────────
    steps = r.get("next_steps", [])
    if steps:
        st.markdown('<div class="section-title">Recommended Next Steps</div>', unsafe_allow_html=True)
        for i, step in enumerate(steps, 1):
            st.markdown(f"**{i}.** {step}")

    # ── Responsible AI — always visible ───────────────────────────────────────
    st.markdown(
        """
        <div class="rai-box">
        ⚖️ <strong>Responsible AI Notice</strong><br>
        This report is AI-generated and may not reflect the most recent events.
        It <strong>augments</strong> human judgment — never replaces it.
        All vendor decisions require review by a qualified procurement analyst.
        This tool should <strong>never</strong> be the sole basis for vendor rejection.
        Every decision is logged for compliance audit purposes.
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(f"Analysis completed: {r.get('timestamp', 'N/A')}")

    # ── Download ──────────────────────────────────────────────────────────────
    st.markdown("")
    vendor_slug = r.get("vendor_name", "vendor").replace(" ", "_")
    ts_slug     = datetime.now().strftime("%Y%m%d_%H%M")
    st.download_button(
        "📥 Download Report (JSON)",
        data=json.dumps(r, indent=2),
        file_name=f"vendorguard_{vendor_slug}_{ts_slug}.json",
        mime="application/json",
    )
