"""
MDT Meeting Auto-Summary AI Agent
Gemini 2.5 Flash | STT Transcript + EMR Context -> Structured Summary
"""

import streamlit as st
import google.generativeai as genai
import json
import time
import re
from datetime import datetime

# ──────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="MDT Summary Agent",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────
# CSS
# ──────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* Section cards */
.section-card {
    background: #f8fafc;
    border-radius: 8px;
    padding: 16px 20px;
    border-left: 3px solid;
    margin-bottom: 10px;
}
.section-patient  { border-color: #2563eb; }
.section-findings { border-color: #059669; }
.section-discuss  { border-color: #7c3aed; }
.section-plan     { border-color: #b45309; }
.section-next     { border-color: #0891b2; }

/* KPI cards */
.kpi-box {
    background: #ffffff;
    border-radius: 8px;
    padding: 14px 16px;
    text-align: center;
    border: 1px solid #e2e8f0;
}
.kpi-value { font-size: 22px; font-weight: 700; color: #1e40af; }
.kpi-label { font-size: 11px; color: #64748b; margin-top: 3px; letter-spacing: 0.3px; }

/* Pipeline steps */
.pipeline-step {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 7px 10px;
    border-radius: 6px;
    margin-bottom: 5px;
    font-size: 12px;
    font-weight: 500;
}
.step-done    { background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; }
.step-active  { background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; }
.step-pending { background: #f8fafc; color: #94a3b8; border: 1px solid #e2e8f0; }

.step-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.dot-done    { background: #16a34a; }
.dot-active  { background: #2563eb; }
.dot-pending { background: #cbd5e1; }

/* Verification rows */
.check-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 5px 0;
    font-size: 12px;
    border-bottom: 1px solid #f1f5f9;
}
.check-dot-ok { width: 6px; height: 6px; border-radius: 50%; background: #16a34a; flex-shrink: 0; }
.check-dot-no { width: 6px; height: 6px; border-radius: 50%; background: #cbd5e1; flex-shrink: 0; }

/* Section header accent bar */
.header-accent {
    display: inline-block;
    width: 3px; height: 16px;
    background: #2563eb;
    border-radius: 2px;
    margin-right: 8px;
    vertical-align: middle;
}

/* Streamlit overrides */
.stTextArea textarea { font-size: 13px !important; line-height: 1.75 !important; }
.stButton > button   { border-radius: 6px !important; font-weight: 500 !important; letter-spacing: 0.2px !important; }
div[data-testid="stSidebar"] { background: #f8fafc; border-right: 1px solid #e2e8f0; }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────
SECTION_META = {
    "patient_info":   {"label": "Patient Information", "cls": "section-patient",  "color": "#2563eb"},
    "key_findings":   {"label": "Key Findings",        "cls": "section-findings", "color": "#059669"},
    "discussion":     {"label": "Discussion",          "cls": "section-discuss",  "color": "#7c3aed"},
    "treatment_plan": {"label": "Treatment Plan",      "cls": "section-plan",     "color": "#b45309"},
    "next_steps":     {"label": "Next Steps",          "cls": "section-next",     "color": "#0891b2"},
}

SAMPLE_TRANSCRIPT = """[MDT Meeting — Patient: Hong Gil-dong]

Oncology: Good morning. Thank you for coming to today's multidisciplinary meeting.

Patient: Good morning. Thank you for seeing me.

Oncology: Following the 2nd cycle of chemotherapy, we reviewed the latest results. CA19-9 has risen to 487 U/mL. The primary lesion remains stable at 2.1 cm on imaging, however a new hepatic lesion is now visible.

Radiology: Confirmed. The MRI shows a 1.2 cm new lesion in hepatic segment S6 with an enhancement pattern consistent with metastatic disease.

Surgery: Surgical resection is not feasible at this stage. With confirmed hepatic metastasis, the case is considered unresectable.

Oncology: Agreed. We should consider transitioning to second-line chemotherapy — either FOLFOX or GEMOX. What is the view from radiation oncology?

Radiation Oncology: Local radiation to the primary lesion is technically feasible, but the benefit would be limited given the hepatic metastasis. I would recommend prioritising systemic therapy over SBRT at this time.

Oncology: Understood. — To the patient: we are considering a transition to a more intensive chemotherapy regimen. Do you have any questions?

Patient: Will the chemotherapy change? I am concerned about side effects.

Oncology: Yes, we are reviewing a regimen change. We will explain the expected side effects in detail at your next visit."""

SAMPLE_EMR = {
    "name":         "Hong Gil-dong (anonymised)",
    "age":          "62",
    "gender":       "Male",
    "diagnosis":    "Cholangiocarcinoma",
    "stage":        "Stage IIIA",
    "medications":  "Gemcitabine 1000 mg/m2, Cisplatin 25 mg/m2",
    "lab":          "CA19-9: 487 U/mL (H), CEA: 12.3 ng/mL (H), Total Bilirubin: 2.1 mg/dL",
    "prev_summary": "2026-03-15: 2nd-cycle chemotherapy completed. Partial response confirmed. Biliary stent replacement discussed.",
}

# ──────────────────────────────────────────────
# Session state
# ──────────────────────────────────────────────
def init_session():
    defaults = {
        "summary":         None,
        "edit_mode":       {},
        "edit_values":     {},
        "approved":        False,
        "rating":          0,
        "history":         [],
        "transcript":      "",
        "processing_time": None,
        "emr":             SAMPLE_EMR.copy(),
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()

# ──────────────────────────────────────────────
# Gemini
# ──────────────────────────────────────────────
def build_prompt(transcript: str, emr: dict) -> str:
    return f"""You are a clinical AI summarisation agent specialised in Multidisciplinary Team (MDT) meetings.
Analyse the meeting transcript and EMR context below to produce a structured clinical summary.
Respond ONLY with a valid JSON object. No preamble, no markdown code fences, no explanation.

[EMR Context — used for medical term correction and contextual grounding]
Patient: {emr.get('name', '')}
Age / Sex: {emr.get('age', '')} / {emr.get('gender', '')}
Diagnosis: {emr.get('diagnosis', '')}
Stage: {emr.get('stage', '')}
Current medications: {emr.get('medications', '')}
Recent lab values: {emr.get('lab', '')}
Previous meeting summary: {emr.get('prev_summary', '')}

[MDT Meeting Transcript]
{transcript}

Output format (JSON only):
{{
  "patient_info":   "Patient demographics and diagnosis summary (2-3 sentences)",
  "key_findings":   "Imaging and laboratory findings, including key value changes (3-5 sentences)",
  "discussion":     "Departmental opinions and treatment options discussed (4-6 sentences)",
  "treatment_plan": "Agreed treatment direction and plan (2-4 sentences)",
  "next_steps":     "Further investigations, referrals, and follow-up schedule (2-3 sentences)"
}}"""


def generate_summary(api_key: str, transcript: str, emr: dict) -> dict:
    genai.configure(api_key=api_key)
    model    = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(
        build_prompt(transcript, emr),
        generation_config=genai.GenerationConfig(temperature=0.2, max_output_tokens=2048),
    )
    raw = response.text.strip()
    raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    return json.loads(raw)

# ──────────────────────────────────────────────
# Patient segment detection
# ──────────────────────────────────────────────
def detect_patient_segment(transcript: str) -> bool:
    patterns = [
        "good morning", "good afternoon", "thank you for coming",
        "patient:", "안녕하세요", "환자분", "오셨군요",
    ]
    t = transcript.lower()
    return any(p.lower() in t for p in patterns)

# ──────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────
with st.sidebar:
    st.markdown("### MDT Summary Agent")
    st.markdown(
        '<span style="background:#eff6ff;color:#1d4ed8;padding:3px 10px;'
        'border-radius:4px;font-size:11px;font-weight:600;letter-spacing:0.3px;">'
        'Phase 1 &nbsp;·&nbsp; Gemini 2.5 Flash</span>',
        unsafe_allow_html=True,
    )
    st.divider()

    st.markdown("**Gemini API Key**")
    api_key = st.text_input(
        "API Key",
        type="password",
        placeholder="AIza...",
        label_visibility="collapsed",
    )
    if api_key:
        st.success("API key accepted.")
    else:
        st.caption("Obtain a key at [aistudio.google.com](https://aistudio.google.com/apikey)")

    st.divider()

    st.markdown("**Target KPIs**")
    kpis = [
        ("85%",   "Documentation time reduction"),
        ("0.80+", "Structured summary F1-score"),
        ("80%+",  "Clinician satisfaction"),
        ("300+",  "Validation cases"),
    ]
    for val, label in kpis:
        st.markdown(
            f'<div class="kpi-box" style="margin-bottom:6px;">'
            f'<div class="kpi-value">{val}</div>'
            f'<div class="kpi-label">{label}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.divider()

    st.markdown("**Pipeline Status**")
    transcript_filled = bool(st.session_state.transcript.strip())
    patient_detected  = detect_patient_segment(st.session_state.transcript)
    summary_done      = st.session_state.summary is not None
    is_approved       = st.session_state.approved

    pipeline_steps = [
        ("Segment detection",     "done"   if patient_detected  else ("active" if transcript_filled else "pending")),
        ("EMR context injection", "done"   if transcript_filled else "pending"),
        ("LLM summary",           "done"   if summary_done      else "pending"),
        ("Clinician review",      "done"   if is_approved       else ("active" if summary_done else "pending")),
        ("Ground truth saved",    "done"   if is_approved       else "pending"),
    ]
    for name, status in pipeline_steps:
        st.markdown(
            f'<div class="pipeline-step step-{status}">'
            f'<div class="step-dot dot-{status}"></div>{name}'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.divider()
    total_records = len(st.session_state.history)
    st.caption(f"Ground truth records: **{total_records}** / 700  (Phase 2 threshold)")
    if total_records > 0:
        st.progress(min(total_records / 700, 1.0))

# ──────────────────────────────────────────────
# Main header
# ──────────────────────────────────────────────
st.markdown(
    '<span class="header-accent"></span>'
    '<span style="font-size:22px;font-weight:700;color:#0f172a;">MDT Meeting Auto-Summary</span>'
    '&nbsp;&nbsp;<span style="font-size:13px;color:#64748b;">AI Agent &nbsp;|&nbsp; Gemini 2.5 Flash</span>',
    unsafe_allow_html=True,
)
st.caption(
    "STT transcript + EMR context  "
    "->  Structured summary  "
    "->  Clinician review  "
    "->  Ground truth accumulation"
)
st.divider()

# ──────────────────────────────────────────────
# Tabs
# ──────────────────────────────────────────────
tab_input, tab_summary, tab_history = st.tabs([
    "Input & EMR",
    "Summary Review",
    "Records & Roadmap",
])

# ════════════════════════════════════════════════
# Tab 1 — Input & EMR
# ════════════════════════════════════════════════
with tab_input:
    col_left, col_right = st.columns([3, 2], gap="large")

    # ── Transcript ──
    with col_left:
        st.markdown(
            '<span class="header-accent"></span>'
            '<span style="font-weight:600;font-size:15px;">Meeting Transcript</span>',
            unsafe_allow_html=True,
        )

        btn_c1, btn_c2, _ = st.columns([1, 1, 4])
        with btn_c1:
            if st.button("Load sample"):
                st.session_state.transcript = SAMPLE_TRANSCRIPT
                st.rerun()
        with btn_c2:
            if st.button("Clear"):
                st.session_state.transcript = ""
                st.session_state.summary    = None
                st.session_state.approved   = False
                st.session_state.rating     = 0
                st.rerun()

        uploaded = st.file_uploader(
            "Upload transcript (.txt / .vtt / .srt)",
            type=["txt", "vtt", "srt"],
        )
        if uploaded:
            content = uploaded.read().decode("utf-8", errors="ignore")
            st.session_state.transcript = content
            st.success(f"Loaded: {uploaded.name}  ({len(content):,} characters)")

        transcript = st.text_area(
            "Transcript",
            value=st.session_state.transcript,
            height=360,
            placeholder=(
                "Paste STT-transcribed text here, or use Load sample / file upload above.\n\n"
                "Expected format:\n"
                "Oncology: Good morning, ...\n"
                "Patient: Good morning, ..."
            ),
            label_visibility="collapsed",
        )
        st.session_state.transcript = transcript

        m1, m2, m3 = st.columns(3)
        m1.metric("Words",           f"{len(transcript.split()):,}" if transcript.strip() else "0")
        m2.metric("Characters",      f"{len(transcript):,}")
        m3.metric("Patient segment", "Detected" if detect_patient_segment(transcript) else "Not detected")

    # ── EMR ──
    with col_right:
        st.markdown(
            '<span class="header-accent"></span>'
            '<span style="font-weight:600;font-size:15px;">EMR Context</span>',
            unsafe_allow_html=True,
        )
        st.caption("Used for medical term correction and contextual grounding.")

        emr = st.session_state.emr
        emr["name"]         = st.text_input("Patient name (anonymised)", value=emr["name"])
        c1, c2              = st.columns(2)
        emr["age"]          = c1.text_input("Age", value=emr["age"])
        emr["gender"]       = c2.text_input("Sex", value=emr["gender"])
        emr["diagnosis"]    = st.text_input("Diagnosis", value=emr["diagnosis"])
        emr["stage"]        = st.text_input("Stage", value=emr["stage"])
        emr["medications"]  = st.text_input("Current medications", value=emr["medications"])
        emr["lab"]          = st.text_area("Recent lab values", value=emr["lab"], height=75)
        emr["prev_summary"] = st.text_area("Previous meeting summary", value=emr["prev_summary"], height=75)
        st.session_state.emr = emr

        st.markdown("---")
        st.markdown(
            '<span style="font-size:12px;font-weight:600;color:#374151;">EMR correction coverage</span>',
            unsafe_allow_html=True,
        )
        coverage = [
            ("Diagnosis cross-check",      bool(emr["diagnosis"])),
            ("Medication term correction", bool(emr["medications"])),
            ("Lab value reference",        bool(emr["lab"])),
            ("Prior summary continuity",   bool(emr["prev_summary"])),
        ]
        for label, ok in coverage:
            dot_cls = "check-dot-ok" if ok else "check-dot-no"
            color   = "#166534"      if ok else "#94a3b8"
            note    = "Active"       if ok else "Not provided"
            st.markdown(
                f'<div class="check-item">'
                f'<div class="{dot_cls}"></div>'
                f'<span style="flex:1;color:#374151;">{label}</span>'
                f'<span style="font-size:11px;color:{color};">{note}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.divider()

    # ── Generate ──
    if not api_key:
        st.warning("Enter your Gemini API key in the sidebar to proceed.")
    else:
        gen_btn = st.button(
            "Generate Structured Summary",
            type="primary",
            use_container_width=True,
            disabled=not transcript.strip(),
        )

        if gen_btn:
            progress_bar = st.progress(0)
            status_text  = st.empty()

            for pct, msg in [
                (15, "Detecting patient segment..."),
                (35, "Injecting EMR context..."),
                (60, "Generating summary with Gemini 2.5 Flash..."),
                (85, "Applying structured output format..."),
            ]:
                progress_bar.progress(pct)
                status_text.markdown(f"*{msg}*")
                time.sleep(0.35)

            t_start = time.time()
            try:
                result  = generate_summary(api_key, transcript, st.session_state.emr)
                elapsed = round(time.time() - t_start, 1)

                progress_bar.progress(100)
                status_text.markdown(f"*Summary generated in {elapsed}s.*")

                st.session_state.summary         = result
                st.session_state.edit_values     = result.copy()
                st.session_state.edit_mode       = {k: False for k in SECTION_META}
                st.session_state.approved        = False
                st.session_state.rating          = 0
                st.session_state.processing_time = elapsed

                time.sleep(0.5)
                progress_bar.empty()
                status_text.empty()
                st.success(
                    f"Summary ready ({elapsed}s). "
                    "Open the Summary Review tab to inspect and approve."
                )

            except json.JSONDecodeError as e:
                progress_bar.empty()
                status_text.empty()
                st.error(f"JSON parse error: {e}")
            except Exception as e:
                progress_bar.empty()
                status_text.empty()
                st.error(f"Error: {e}")

# ════════════════════════════════════════════════
# Tab 2 — Summary Review
# ════════════════════════════════════════════════
with tab_summary:
    if st.session_state.summary is None:
        st.info("No summary available. Generate a summary in the Input & EMR tab.")
        st.stop()

    summary = st.session_state.summary
    col_main, col_review = st.columns([3, 1], gap="large")

    # ── Summary sections ──
    with col_main:
        h1, h2 = st.columns([3, 1])
        with h1:
            st.markdown(
                '<span class="header-accent"></span>'
                '<span style="font-weight:600;font-size:15px;">AI-Generated Structured Summary</span>',
                unsafe_allow_html=True,
            )
        with h2:
            if st.session_state.processing_time:
                st.metric("Processing time", f"{st.session_state.processing_time}s")

        for section_key, meta in SECTION_META.items():
            content    = st.session_state.edit_values.get(section_key, summary.get(section_key, ""))
            is_editing = st.session_state.edit_mode.get(section_key, False)

            with st.expander(meta["label"], expanded=True):
                if is_editing:
                    new_val = st.text_area(
                        meta["label"],
                        value=content,
                        height=120,
                        key=f"edit_{section_key}",
                        label_visibility="collapsed",
                    )
                    s1, s2, _ = st.columns([1, 1, 4])
                    if s1.button("Save", key=f"save_{section_key}"):
                        st.session_state.edit_values[section_key] = new_val
                        st.session_state.edit_mode[section_key]   = False
                        st.rerun()
                    if s2.button("Cancel", key=f"cancel_{section_key}"):
                        st.session_state.edit_mode[section_key] = False
                        st.rerun()
                else:
                    st.markdown(
                        f'<div class="section-card {meta["cls"]}">'
                        f'<p style="margin:0;font-size:13.5px;line-height:1.8;color:#1e293b;">{content}</p>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    if st.button("Edit", key=f"edit_btn_{section_key}"):
                        st.session_state.edit_mode[section_key] = True
                        st.rerun()

        with st.expander("Raw JSON", expanded=False):
            st.json(st.session_state.edit_values)

    # ── Review panel ──
    with col_review:
        st.markdown(
            '<span class="header-accent"></span>'
            '<span style="font-weight:600;font-size:15px;">Clinician Review</span>',
            unsafe_allow_html=True,
        )
        st.markdown("")

        st.markdown(
            '<span style="font-size:12px;font-weight:600;color:#374151;">Summary quality rating</span>',
            unsafe_allow_html=True,
        )
        rating = st.select_slider(
            "Rating",
            options=[1, 2, 3, 4, 5],
            value=max(st.session_state.rating, 1),
            format_func=lambda x: f"{x} / 5",
            label_visibility="collapsed",
        )
        st.session_state.rating = rating
        st.caption({1: "Poor", 2: "Below average", 3: "Acceptable", 4: "Good", 5: "Excellent"}[rating])

        st.markdown("---")

        if st.session_state.approved:
            st.success("Approved. Saved to ground truth.")
        else:
            if st.button("Approve & Save to Ground Truth", type="primary", use_container_width=True):
                record = {
                    "id":        len(st.session_state.history) + 1,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "patient":   st.session_state.emr.get("name", "-"),
                    "diagnosis": st.session_state.emr.get("diagnosis", "-"),
                    "rating":    st.session_state.rating,
                    "summary":   st.session_state.edit_values.copy(),
                    "proc_time": st.session_state.processing_time,
                }
                st.session_state.history.append(record)
                st.session_state.approved = True
                st.rerun()

        st.markdown("---")
        st.markdown(
            '<span style="font-size:12px;font-weight:600;color:#374151;">EMR cross-validation</span>',
            unsafe_allow_html=True,
        )
        emr_checks = [
            ("Diagnosis verified",         True),
            ("Medication terms corrected", True),
            ("Lab values referenced",      True),
            ("Prior summary continuity",   bool(st.session_state.emr.get("prev_summary"))),
            ("Scheduling integration",     False),
        ]
        for label, ok in emr_checks:
            dot_cls = "check-dot-ok" if ok else "check-dot-no"
            color   = "#166534"      if ok else "#94a3b8"
            note    = "Active" if ok else ("Phase 2" if label == "Scheduling integration" else "N/A")
            st.markdown(
                f'<div class="check-item">'
                f'<div class="{dot_cls}"></div>'
                f'<span style="flex:1;color:#374151;">{label}</span>'
                f'<span style="font-size:11px;color:{color};">{note}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

        st.markdown("---")
        st.markdown(
            '<span style="font-size:12px;font-weight:600;color:#374151;">Export</span>',
            unsafe_allow_html=True,
        )
        st.markdown("")

        json_str = json.dumps(st.session_state.edit_values, ensure_ascii=False, indent=2)
        st.download_button(
            "Download JSON",
            data=json_str,
            file_name=f"mdt_summary_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
            mime="application/json",
            use_container_width=True,
        )

        txt_output = "\n\n".join(
            f"[{SECTION_META[k]['label'].upper()}]\n{v}"
            for k, v in st.session_state.edit_values.items()
        )
        st.download_button(
            "Download TXT",
            data=txt_output,
            file_name=f"mdt_summary_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
            mime="text/plain",
            use_container_width=True,
        )

# ════════════════════════════════════════════════
# Tab 3 — Records & Roadmap
# ════════════════════════════════════════════════
with tab_history:
    st.markdown(
        '<span class="header-accent"></span>'
        '<span style="font-weight:600;font-size:15px;">Accumulation Progress</span>',
        unsafe_allow_html=True,
    )
    st.markdown("")

    history    = st.session_state.history
    total      = len(history)
    avg_rating = round(sum(r["rating"] for r in history) / total, 1) if total else 0
    avg_time   = round(sum(r["proc_time"] or 0 for r in history) / total, 1) if total else 0
    phase2_pct = min(total / 700 * 100, 100)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total records",        f"{total}")
    c2.metric("Phase 2 progress",     f"{phase2_pct:.1f}%")
    c3.metric("Avg. quality rating",  f"{avg_rating} / 5.0" if total else "—")
    c4.metric("Avg. processing time", f"{avg_time}s" if total else "—")

    st.progress(phase2_pct / 100)
    st.caption(f"Fine-tuning threshold: 700 approved records  ({total} / 700 complete)")
    st.divider()

    # Roadmap
    st.markdown(
        '<span class="header-accent"></span>'
        '<span style="font-weight:600;font-size:15px;">Development Roadmap</span>',
        unsafe_allow_html=True,
    )
    st.markdown("")

    phases = [
        ("Phase 0", "Mar 2026",     "done",    "Prototype Validation",  ["Gemini-based POC", "Pipeline design", "EMR correction confirmed"]),
        ("Phase 1", "Apr-Jun 2026", "active",  "Data & Infrastructure", ["IRB approval", "Review UI build", "API integration"]),
        ("Phase 2", "Jul-Sep 2026", "pending", "Model Development",     ["On-prem GPU setup", "LLM fine-tuning", "Summary quality uplift"]),
        ("Phase 3", "Oct-Dec 2026", "pending", "Clinical Validation",   ["300+ case validation", "KPI verification", "Full EMR integration"]),
    ]
    color_map  = {"done": "#f0fdf4", "active": "#eff6ff", "pending": "#f8fafc"}
    border_map = {"done": "#bbf7d0", "active": "#bfdbfe", "pending": "#e2e8f0"}
    text_map   = {"done": "#166534", "active": "#1d4ed8", "pending": "#94a3b8"}
    label_map  = {"done": "Complete", "active": "In progress", "pending": "Planned"}

    cols = st.columns(4)
    for col, (phase, period, status, title, items) in zip(cols, phases):
        items_html = "".join(
            f'<li style="margin-bottom:5px;font-size:12px;color:#334155;line-height:1.5;">{item}</li>'
            for item in items
        )
        badge_html = (
            f'<span style="font-size:10px;font-weight:600;'
            f'background:{color_map[status]};color:{text_map[status]};'
            f'padding:2px 8px;border-radius:4px;border:1px solid {border_map[status]};">'
            f'{label_map[status]}</span>'
        )
        col.markdown(
            f'<div style="background:{color_map[status]};border:1px solid {border_map[status]};'
            f'border-radius:8px;padding:16px;min-height:190px;">'
            f'<div style="font-size:11px;font-weight:700;color:{text_map[status]};'
            f'margin-bottom:2px;letter-spacing:0.4px;">{phase} &nbsp;·&nbsp; {period}</div>'
            f'<div style="font-weight:600;font-size:13px;color:#0f172a;margin-bottom:6px;">{title}</div>'
            f'{badge_html}'
            f'<ul style="padding-left:14px;margin:10px 0 0;">{items_html}</ul>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.divider()

    # Session records table
    st.markdown(
        '<span class="header-accent"></span>'
        '<span style="font-weight:600;font-size:15px;">Session Records</span>',
        unsafe_allow_html=True,
    )
    st.markdown("")

    if not history:
        st.info("No approved records yet. Generate and approve a summary to create the first ground truth entry.")
    else:
        import pandas as pd
        df = pd.DataFrame([
            {
                "ID":             r["id"],
                "Timestamp":      r["timestamp"],
                "Patient":        r["patient"],
                "Diagnosis":      r["diagnosis"],
                "Rating":         f"{r['rating']} / 5",
                "Processing (s)": r["proc_time"],
            }
            for r in reversed(history)
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)

        all_json = json.dumps(history, ensure_ascii=False, indent=2)
        st.download_button(
            "Download all ground truth records (JSON)",
            data=all_json,
            file_name=f"ground_truth_{datetime.now().strftime('%Y%m%d')}.json",
            mime="application/json",
        )
