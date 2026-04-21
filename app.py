"""
MDT Meeting Auto-Summary — Clinical Annotation Dashboard
Gemini API | STT Transcript → Structured Summary → Clinician Review
"""

import streamlit as st
import google.generativeai as genai
import json, re, time, os
from datetime import datetime
from pathlib import Path

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────
GEMINI_API_KEY = "AIzaSyCDpVePKnZAY3kTxRoal0LgDu7jB8B2zD8"
UPLOAD_DIR     = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

st.set_page_config(
    page_title="MDT Annotation Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────
# CSS
# ──────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.section-card {
    background: #f8fafc; border-radius: 8px;
    padding: 14px 18px; border-left: 3px solid; margin-bottom: 8px;
}
.section-patient  { border-color: #2563eb; }
.section-findings { border-color: #059669; }
.section-discuss  { border-color: #7c3aed; }
.section-plan     { border-color: #b45309; }
.section-next     { border-color: #0891b2; }

.transcript-box {
    background: #1e293b; border-radius: 8px;
    padding: 14px 16px; font-size: 12.5px; line-height: 1.85;
    color: #e2e8f0; white-space: pre-wrap; max-height: 400px;
    overflow-y: auto; font-family: monospace;
}
.case-card {
    border: 1px solid #e2e8f0; border-radius: 8px;
    padding: 12px 14px; margin-bottom: 6px;
}
.badge {
    display: inline-block; padding: 2px 9px; border-radius: 4px;
    font-size: 11px; font-weight: 600; letter-spacing: 0.2px;
}
.badge-done    { background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; }
.badge-pending { background: #fef9c3; color: #854d0e; border: 1px solid #fde68a; }
.badge-active  { background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; }
.kpi-box {
    background: #fff; border-radius: 8px; padding: 14px 16px;
    text-align: center; border: 1px solid #e2e8f0;
}
.kpi-value { font-size: 22px; font-weight: 700; color: #1e40af; }
.kpi-label { font-size: 11px; color: #64748b; margin-top: 3px; }
.pipeline-step {
    display: flex; align-items: center; gap: 8px;
    padding: 7px 10px; border-radius: 6px; margin-bottom: 5px;
    font-size: 12px; font-weight: 500;
}
.step-done    { background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; }
.step-active  { background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; }
.step-pending { background: #f8fafc; color: #94a3b8; border: 1px solid #e2e8f0; }
.step-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.dot-done    { background: #16a34a; }
.dot-active  { background: #2563eb; }
.dot-pending { background: #cbd5e1; }
.header-accent {
    display: inline-block; width: 3px; height: 16px;
    background: #2563eb; border-radius: 2px;
    margin-right: 8px; vertical-align: middle;
}
.emr-api-notice {
    background: #eff6ff; border: 1px solid #bfdbfe;
    border-left: 4px solid #2563eb; border-radius: 6px;
    padding: 10px 14px; margin-bottom: 10px;
    font-size: 12px; color: #1e40af; line-height: 1.6;
}
.check-row {
    display: flex; align-items: center; gap: 8px;
    padding: 4px 0; font-size: 12px;
    border-bottom: 1px solid #f1f5f9;
}
.dot-ok { width:6px;height:6px;border-radius:50%;background:#16a34a;flex-shrink:0; }
.dot-no { width:6px;height:6px;border-radius:50%;background:#cbd5e1;flex-shrink:0; }
.stTextArea textarea { font-size: 13px !important; line-height: 1.75 !important; }
.stButton > button   { border-radius: 6px !important; font-weight: 500 !important; }
div[data-testid="stSidebar"] { background: #f8fafc; border-right: 1px solid #e2e8f0; }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────
SECTION_META = {
    "patient_info":   {"label": "Patient Information", "cls": "section-patient"},
    "key_findings":   {"label": "Key Findings",        "cls": "section-findings"},
    "discussion":     {"label": "Discussion",          "cls": "section-discuss"},
    "treatment_plan": {"label": "Treatment Plan",      "cls": "section-plan"},
    "next_steps":     {"label": "Next Steps",          "cls": "section-next"},
}

# EMR fields aligned with EMR Summary Agent I/O
# Input  fields: patient_information, procedure, surgery, chemotherapy,
#                radiation, imaging, biopsies, blood, history, medication
# Output fields: comprehensive_summary, current_status, progress_record,
#                key_procedures, consultation_issues
EMR_FIELDS = [
    ("diagnosis",       "진단명",           "예: 담관세포암 (Cholangiocarcinoma)",     False),
    ("stage",           "병기",             "예: Stage II, T2N0M0",                   False),
    ("chief_complaint", "주호소 / 현병력",   "예: 황달, 복통 3주",                      False),
    ("imaging",         "영상 소견 요약",    "예: MRI — 담관 내 종양 2.3cm, 혈관 침범 없음", True),
    ("biopsies",        "조직검사 결과",     "예: EUS-FNA — 선암종 (Adenocarcinoma)",   True),
    ("blood",           "주요 혈액검사",     "예: CA19-9: 110→67 U/mL, T-Bili: 2.3",   True),
    ("procedure",       "시술 내역",         "예: ERCP + 담도 스텐트 삽입 (2026-03-01)", False),
    ("surgery",         "수술 내역",         "예: -",                                   False),
    ("chemotherapy",    "항암 치료 내역",    "예: Gemcitabine + Cisplatin 1차 완료",     False),
    ("radiation",       "방사선 치료 내역",  "예: -",                                   False),
    ("medication",      "현재 투약",         "예: 젬시타빈 1000mg/m², 시스플라틴 25mg/m²", False),
    ("history",         "과거력 / 기타",     "예: 고혈압, 당뇨 없음",                    True),
]

EMPTY_EMR = {key: "" for key, *_ in EMR_FIELDS}

# ──────────────────────────────────────────────
# EMR API Placeholder
# ──────────────────────────────────────────────
# TODO: Replace get_emr_context() body with actual API call when ready.
#
# Mode A — Raw EMR API
#   Endpoint : GET /v1/patient/{patient_id}
#   Returns  : {diagnosis, stage, chief_complaint, imaging, biopsies,
#               blood, procedure, surgery, chemotherapy, radiation,
#               medication, history}
#
# Mode B — EMR Summary Agent API
#   Endpoint : GET /v1/summary/{patient_id}
#   Returns  : {comprehensive_summary, current_status, progress_record,
#               key_procedures, consultation_issues}
#   → Map these into EMR_FIELDS for contextual grounding in build_prompt().
#
# def fetch_emr_from_api(patient_id: str, mode: str = "summary") -> dict:
#     import requests
#     headers = {"Authorization": f"Bearer {EMR_API_TOKEN}"}
#     if mode == "summary":
#         data = requests.get(
#             f"https://emr-api.hospital.internal/v1/summary/{patient_id}", headers=headers
#         ).json()
#         return {
#             "diagnosis":       data.get("comprehensive_summary", ""),
#             "stage":           data.get("current_status", ""),
#             "imaging":         data.get("key_procedures", ""),
#             "history":         data.get("progress_record", ""),
#             "chief_complaint": data.get("consultation_issues", ""),
#         }
#     else:
#         data = requests.get(
#             f"https://emr-api.hospital.internal/v1/patient/{patient_id}", headers=headers
#         ).json()
#         return {key: data.get(key, "") for key, *_ in EMR_FIELDS}

def get_emr_context() -> dict:
    """Entry point. Swap body with fetch_emr_from_api() when API is ready."""
    return st.session_state.get("emr", EMPTY_EMR.copy())

# ──────────────────────────────────────────────
# Session state
# ──────────────────────────────────────────────
def init_session():
    defaults = {
        "cases":         {},    # {fname: {transcript, segment, detected, summary, edit_values, approved, rating, proc_time, timestamp}}
        "selected_case": None,
        "emr":           EMPTY_EMR.copy(),
        "edit_mode":     {k: False for k in SECTION_META},
        "history":       [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
def detect_consultation_segment(transcript: str) -> tuple:
    """
    Detect patient consultation segment (환자 진료 구간).
    The greeting pattern (의사→환자 인사) marks the start of the clinical portion.
    Returns (detected: bool, segment_text: str).
    """
    patterns = ["안녕하세요", "안녕하십니까", "반갑습니다", "오셨군요", "환자분"]
    lines    = transcript.splitlines()
    for i, line in enumerate(lines):
        if any(p in line for p in patterns):
            return True, "\n".join(lines[i:]).strip()
    return False, ""

def safe_parse_json(raw: str) -> dict:
    """Robustly parse JSON from LLM output, handling all common failure modes."""
    # 1. Strip markdown fences
    cleaned = re.sub(r"^```(?:json)?", "", raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"```$", "", cleaned.strip(), flags=re.MULTILINE).strip()

    # 2. Direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 3. Extract outermost JSON object
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        candidate = match.group(0)
        # Fix trailing commas
        candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
        # Fix unterminated strings: find the last complete key-value pair
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            # Attempt to salvage by truncating to last valid closing brace
            for end in range(len(candidate) - 1, 0, -1):
                if candidate[end] == "}":
                    try:
                        return json.loads(candidate[:end + 1])
                    except json.JSONDecodeError:
                        continue

    # 4. Key-by-key regex fallback
    result = {}
    for key in SECTION_META:
        m = re.search(rf'"{key}"\s*:\s*"((?:[^"\\]|\\.)*)(?:"|$)', cleaned, re.DOTALL)
        if m:
            result[key] = m.group(1).replace('\\"', '"').replace("\\n", "\n")
    if result:
        return result

    raise ValueError(f"LLM 응답을 파싱할 수 없습니다.\n\n원본:\n{raw[:600]}")

def build_prompt(segment: str, emr: dict) -> str:
    emr_block = "\n".join(
        f"{label}: {emr.get(key, '') or '-'}"
        for key, label, _, _ in EMR_FIELDS
        if emr.get(key, "").strip()
    ) or "(EMR 정보 없음)"

    return f"""You are a clinical AI specialised in Korean Multidisciplinary Team (MDT) meetings.
Given the patient consultation segment (환자 진료 구간) and EMR context, produce a structured summary.
Output ONLY a raw JSON object. No markdown. No code fences. No explanation. No text before or after the JSON.

[EMR Context]
{emr_block}

[환자 진료 구간]
{segment[:8000]}

Return exactly this JSON (all values in Korean, use "-" if unknown):
{{"patient_info":"환자 기본 정보 및 진단 요약 2~3문장","key_findings":"영상 및 검사 소견 3~5문장","discussion":"각 과별 의견 및 논의 옵션 4~6문장","treatment_plan":"확정 치료 방향 2~4문장","next_steps":"추가 검사 및 다음 일정 2~3문장"}}"""

def run_summary(segment: str, emr: dict) -> dict:
    genai.configure(api_key=GEMINI_API_KEY)
    model    = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(
        build_prompt(segment, emr),
        generation_config=genai.GenerationConfig(temperature=0.1, max_output_tokens=2048),
    )
    result = safe_parse_json(response.text)
    for key in SECTION_META:
        if key not in result or not str(result.get(key, "")).strip():
            result[key] = "-"
    return result

def list_cases() -> list:
    return sorted([f.name for f in UPLOAD_DIR.glob("*.txt")])

def load_transcript(fname: str) -> str:
    p = UPLOAD_DIR / fname
    return p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""

# ══════════════════════════════════════════════
# Sidebar
# ══════════════════════════════════════════════
with st.sidebar:
    st.markdown(
        '<div style="font-size:16px;font-weight:700;color:#ffffff;margin-bottom:4px;">MDT Annotation Dashboard</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<span class="badge badge-active">Phase 1 &nbsp;·&nbsp; Gemini API</span>',
        unsafe_allow_html=True,
    )
    st.divider()

    nav = st.radio(
        "nav", ["📤  File Upload", "🔍  Case Review", "📊  Records & Roadmap"],
        label_visibility="collapsed",
    )
    st.divider()

    sel  = st.session_state.selected_case
    case = st.session_state.cases.get(sel, {}) if sel else {}
    steps = [
        ("Transcript loaded",                      bool(case.get("transcript"))),
        ("Consultation segment detected",           bool(case.get("segment"))),
        ("EMR context set",                         any(v for v in st.session_state.emr.values())),
        ("AI summary generated",                   bool(case.get("summary"))),
        ("Clinician review complete",              bool(case.get("approved"))),
    ]
    st.markdown("**Pipeline Status**")
    for name, done in steps:
        s = "done" if done else "pending"
        st.markdown(
            f'<div class="pipeline-step step-{s}"><div class="step-dot dot-{s}"></div>{name}</div>',
            unsafe_allow_html=True,
        )
    st.divider()
    total = len(st.session_state.history)
    st.caption(f"Approved records: **{total}** / 700")
    if total:
        st.progress(min(total / 700, 1.0))

# ──────────────────────────────────────────────
# Header
# ──────────────────────────────────────────────
st.markdown(
    '<span class="header-accent"></span>'
    '<span style="font-size:21px;font-weight:700;color:#ffffff;">MDT Meeting Auto-Summary</span>'
    '&nbsp;<span style="font-size:13px;color:#ffffff;">Annotation Dashboard</span>',
    unsafe_allow_html=True,
)
st.divider()

# ══════════════════════════════════════════════
# File Upload Tab
# ══════════════════════════════════════════════
if nav == "📤  File Upload":
    st.markdown(
        '<span class="header-accent"></span>'
        '<span style="font-weight:600;font-size:15px;">Transcript File Management</span>',
        unsafe_allow_html=True,
    )
    st.caption("STT 전사 파일을 미리 업로드해 두는 공간입니다. Case Review 탭에서 파일을 선택해 검수를 진행하세요.")
    st.markdown("")

    col_up, col_list = st.columns(2, gap="large")

    with col_up:
        st.markdown("**파일 업로드**")
        uploaded_files = st.file_uploader(
            "STT 전사 파일 (.txt / .vtt / .srt)",
            type=["txt", "vtt", "srt"],
            accept_multiple_files=True,
            label_visibility="collapsed",
        )
        if uploaded_files:
            for f in uploaded_files:
                (UPLOAD_DIR / f.name).write_bytes(f.read())
                st.success(f"✓ {f.name} 업로드 완료")

    with col_list:
        st.markdown("**업로드된 파일 목록**")
        files = list_cases()
        if not files:
            st.info("업로드된 파일이 없습니다.")
        else:
            for fname in files:
                c1, c2 = st.columns([5, 1])
                c1.markdown(f"📄 `{fname}`")
                if c2.button("삭제", key=f"del_{fname}"):
                    (UPLOAD_DIR / fname).unlink(missing_ok=True)
                    if fname in st.session_state.cases:
                        del st.session_state.cases[fname]
                    if st.session_state.selected_case == fname:
                        st.session_state.selected_case = None
                    st.rerun()

# ══════════════════════════════════════════════
# Case Review Tab
# ══════════════════════════════════════════════
elif nav == "🔍  Case Review":
    files = list_cases()
    if not files:
        st.warning("업로드된 전사 파일이 없습니다. **File Upload** 탭에서 파일을 먼저 업로드하세요.")
        st.stop()

    col_sel, col_main = st.columns([1, 3], gap="large")

    # ── Case list ──────────────────────────────────
    with col_sel:
        st.markdown(
            '<span class="header-accent"></span>'
            '<span style="font-weight:600;font-size:14px;">Case List</span>',
            unsafe_allow_html=True,
        )
        for fname in files:
            cd       = st.session_state.cases.get(fname, {})
            approved = cd.get("approved", False)
            has_sum  = bool(cd.get("summary"))
            badge    = "badge-done" if approved else ("badge-active" if has_sum else "badge-pending")
            label    = "Approved"   if approved else ("Generated"   if has_sum else "Pending")
            is_sel   = st.session_state.selected_case == fname

            st.markdown(
                f'<div class="case-card" style="{"background:#eff6ff;border-color:#2563eb;" if is_sel else ""}">'
                f'<div style="font-size:12px;font-weight:600;color:#1e293b;margin-bottom:4px;">{fname}</div>'
                f'<span class="badge {badge}">{label}</span>'
                f'</div>', unsafe_allow_html=True,
            )
            if st.button("선택", key=f"sel_{fname}", use_container_width=True):
                st.session_state.selected_case = fname
                if fname not in st.session_state.cases:
                    raw      = load_transcript(fname)
                    det, seg = detect_consultation_segment(raw)
                    st.session_state.cases[fname] = {
                        "transcript": raw, "segment": seg, "detected": det,
                        "summary": None, "edit_values": {},
                        "approved": False, "rating": 0,
                        "proc_time": None, "timestamp": None,
                    }
                st.session_state.edit_mode = {k: False for k in SECTION_META}
                st.rerun()

    # ── Main area ──────────────────────────────────
    with col_main:
        sel = st.session_state.selected_case
        if not sel:
            st.info("좌측에서 케이스를 선택하세요.")
            st.stop()

        case = st.session_state.cases[sel]

        t1, t2, t3 = st.tabs(["📋  Transcript & Segment", "🗂  EMR Context", "🤖  AI Summary Review"])

        # ── Transcript & Segment ────────────────────
        with t1:
            st.markdown(
                f'<span class="header-accent"></span>'
                f'<span style="font-weight:600;font-size:14px;">{sel}</span>',
                unsafe_allow_html=True,
            )
            if case.get("detected"):
                st.success("✓ 환자 진료 구간(Clinical Consultation Segment) 자동 탐지 완료")
            else:
                st.warning("⚠ 자동 탐지 실패. 아래 우측 패널에서 진료 구간을 직접 지정하세요.")

            l, r = st.columns(2, gap="medium")
            with l:
                st.markdown("**전체 전사 텍스트**")
                st.markdown(
                    f'<div class="transcript-box">{case["transcript"]}</div>',
                    unsafe_allow_html=True,
                )
            with r:
                st.markdown("**환자 진료 구간 ← Ground Truth 기준**")
                st.caption("이 구간이 AI 요약의 입력이며 검수의 정답 기준입니다. 필요 시 직접 수정하세요.")
                new_seg = st.text_area(
                    "seg", value=case.get("segment", ""),
                    height=380, label_visibility="collapsed",
                )
                if new_seg != case.get("segment", ""):
                    st.session_state.cases[sel]["segment"] = new_seg
                    st.session_state.cases[sel]["detected"] = bool(new_seg.strip())
                st.caption(f"구간 길이: {len(new_seg.split()):,} words")

        # ── EMR Context ─────────────────────────────
        with t2:
            st.markdown(
                '<div class="emr-api-notice">'
                '🔌 <b>EMR API 연동 예정</b><br>'
                '현재는 수동 입력 방식입니다. 향후 Raw EMR API 또는 EMR 요약 에이전트 API로 자동 대체됩니다.<br>'
                '<span style="font-size:11px;">EMR 요약 에이전트 출력: 종합 요약 / 현재 상태 / 경과 기록 / 주요 검사·시술 / 협진 쟁점</span>'
                '</div>', unsafe_allow_html=True,
            )

            emr_mode = st.radio(
                "emr_mode",
                ["수동 입력 (현재)", "Raw EMR API (준비 중)", "EMR 요약 에이전트 API (준비 중)"],
                horizontal=True, label_visibility="collapsed",
            )

            if emr_mode != "수동 입력 (현재)":
                st.info(
                    "API 연동 준비 중입니다.\n\n"
                    "**Raw EMR API** — 진단명, 병기, 영상, 조직검사, 혈액검사, 시술, 수술, 항암, 방사선, 투약, 병력 직접 수신\n\n"
                    "**EMR 요약 에이전트 API** — 종합 요약 / 현재 상태 / 경과 기록 / 주요 검사·시술 / 협진 쟁점 수신"
                )
            else:
                emr = st.session_state.emr
                ca, cb = st.columns(2, gap="medium")
                for i, (key, label, placeholder, is_long) in enumerate(EMR_FIELDS):
                    col = ca if i % 2 == 0 else cb
                    with col:
                        if is_long:
                            emr[key] = st.text_area(
                                label, value=emr.get(key, ""),
                                placeholder=placeholder, height=80, key=f"emr_{key}",
                            )
                        else:
                            emr[key] = st.text_input(
                                label, value=emr.get(key, ""),
                                placeholder=placeholder, key=f"emr_{key}",
                            )
                st.session_state.emr = emr
                filled = sum(1 for k, *_ in EMR_FIELDS if emr.get(k, "").strip())
                st.progress(filled / len(EMR_FIELDS))
                st.caption(f"EMR 항목 입력: {filled} / {len(EMR_FIELDS)}")

        # ── AI Summary Review ───────────────────────
        with t3:
            if not case.get("segment", "").strip():
                st.warning("Transcript & Segment 탭에서 환자 진료 구간을 먼저 지정하세요.")
                st.stop()

            gen_col, _ = st.columns([2, 3])
            with gen_col:
                gen_btn = st.button(
                    "🤖  Generate Structured Summary",
                    type="primary", use_container_width=True,
                    disabled=bool(case.get("approved")),
                )

            if gen_btn:
                pb, stat = st.progress(0), st.empty()
                for pct, msg in [(20,"환자 진료 구간 확인 중..."),(45,"EMR 맥락 주입 중..."),(70,"Gemini API 요약 생성 중..."),(90,"구조화 포맷 적용 중...")]:
                    pb.progress(pct); stat.markdown(f"*{msg}*"); time.sleep(0.3)
                t0 = time.time()
                try:
                    result  = run_summary(case["segment"], get_emr_context())
                    elapsed = round(time.time() - t0, 1)
                    pb.progress(100); stat.markdown(f"*완료 ({elapsed}s)*"); time.sleep(0.4)
                    pb.empty(); stat.empty()
                    st.session_state.cases[sel].update({
                        "summary": result, "edit_values": result.copy(),
                        "approved": False, "rating": 0,
                        "proc_time": elapsed, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    })
                    st.session_state.edit_mode = {k: False for k in SECTION_META}
                    st.success(f"요약 생성 완료 ({elapsed}s) — 아래에서 검수 후 승인하세요.")
                    st.rerun()
                except Exception as e:
                    pb.empty(); stat.empty()
                    st.error(f"오류: {e}")

            if not case.get("summary"):
                st.info("Generate 버튼을 눌러 AI 요약을 생성하세요.")
                st.stop()

            st.markdown("---")
            ann_col, ctrl_col = st.columns([3, 1], gap="large")

            with ann_col:
                st.markdown(
                    '<span class="header-accent"></span>'
                    '<span style="font-weight:600;font-size:14px;">AI 생성 요약 — 검수 및 수정</span>',
                    unsafe_allow_html=True,
                )
                if case.get("proc_time"):
                    st.caption(f"생성 시간: {case['proc_time']}s  ·  {case.get('timestamp','')}")

                edit_mode = st.session_state.edit_mode

                for sk, meta in SECTION_META.items():
                    content    = case["edit_values"].get(sk, "")
                    is_editing = edit_mode.get(sk, False)
                    is_approved = case.get("approved", False)

                    with st.expander(f"**{meta['label']}**", expanded=True):
                        if is_approved or not is_editing:
                            st.markdown(
                                f'<div class="section-card {meta["cls"]}">'
                                f'<p style="margin:0;font-size:13px;line-height:1.8;color:#1e293b;">{content}</p>'
                                f'</div>', unsafe_allow_html=True,
                            )
                            if not is_approved:
                                if st.button("✏ 수정", key=f"eb_{sk}"):
                                    st.session_state.edit_mode[sk] = True
                                    st.rerun()
                        else:
                            new_val = st.text_area(
                                meta["label"], value=content, height=120,
                                key=f"ea_{sk}", label_visibility="collapsed",
                            )
                            s1, s2, _ = st.columns([1, 1, 4])
                            if s1.button("저장", key=f"sv_{sk}"):
                                st.session_state.cases[sel]["edit_values"][sk] = new_val
                                st.session_state.edit_mode[sk] = False
                                st.rerun()
                            if s2.button("취소", key=f"cn_{sk}"):
                                st.session_state.edit_mode[sk] = False
                                st.rerun()

                with st.expander("Raw JSON", expanded=False):
                    st.json(case["edit_values"])

            with ctrl_col:
                st.markdown(
                    '<span class="header-accent"></span>'
                    '<span style="font-weight:600;font-size:14px;">Annotation Panel</span>',
                    unsafe_allow_html=True,
                )
                st.markdown("**요약 품질 평가**")
                rating = st.select_slider(
                    "r", options=[1,2,3,4,5],
                    value=max(case.get("rating",1),1),
                    format_func=lambda x: f"{x}/5",
                    label_visibility="collapsed",
                )
                st.session_state.cases[sel]["rating"] = rating
                st.caption({1:"Poor",2:"Below avg",3:"Acceptable",4:"Good",5:"Excellent"}[rating])

                st.markdown("---")
                st.markdown("**Ground Truth 정합성**")
                checks = [
                    ("진단명 일치",   bool(case["edit_values"].get("patient_info"))),
                    ("검사 소견 반영", bool(case["edit_values"].get("key_findings"))),
                    ("논의 내용 포함", bool(case["edit_values"].get("discussion"))),
                    ("치료 계획 명시", bool(case["edit_values"].get("treatment_plan"))),
                    ("다음 단계 기재", bool(case["edit_values"].get("next_steps"))),
                ]
                for lbl, ok in checks:
                    dot = "dot-ok" if ok else "dot-no"
                    col = "#166534" if ok else "#94a3b8"
                    st.markdown(
                        f'<div class="check-row"><div class="{dot}"></div>'
                        f'<span style="flex:1;color:#374151;">{lbl}</span>'
                        f'<span style="color:{col};font-weight:600;">{"✓" if ok else "—"}</span></div>',
                        unsafe_allow_html=True,
                    )

                st.markdown("---")
                if case.get("approved"):
                    st.success("✅ 승인 완료\nGround Truth 저장됨")
                    if st.button("승인 취소", use_container_width=True):
                        st.session_state.cases[sel]["approved"] = False
                        st.rerun()
                else:
                    if st.button("✅ 승인 & GT 저장", type="primary", use_container_width=True):
                        record = {
                            "id":             len(st.session_state.history) + 1,
                            "timestamp":      datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "filename":       sel,
                            "emr":            st.session_state.emr.copy(),
                            "segment":        case["segment"],
                            "ai_summary":     case["summary"],
                            "final_summary":  case["edit_values"].copy(),
                            "rating":         rating,
                            "proc_time":      case.get("proc_time"),
                        }
                        st.session_state.history.append(record)
                        st.session_state.cases[sel]["approved"] = True
                        st.rerun()

                st.markdown("---")
                st.markdown("**Export**")
                js = json.dumps(case["edit_values"], ensure_ascii=False, indent=2)
                st.download_button("JSON", data=js,
                    file_name=f"mdt_{sel}_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                    mime="application/json", use_container_width=True)
                txt = "\n\n".join(
                    f"[{SECTION_META[k]['label'].upper()}]\n{v}"
                    for k, v in case["edit_values"].items()
                )
                st.download_button("TXT", data=txt,
                    file_name=f"mdt_{sel}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                    mime="text/plain", use_container_width=True)

# ══════════════════════════════════════════════
# Records & Roadmap Tab
# ══════════════════════════════════════════════
elif nav == "📊  Records & Roadmap":
    st.markdown(
        '<span class="header-accent"></span>'
        '<span style="font-weight:600;font-size:15px;">Accumulation Progress</span>',
        unsafe_allow_html=True,
    )
    history = st.session_state.history
    total   = len(history)
    avg_r   = round(sum(r["rating"] for r in history) / total, 1) if total else 0
    avg_t   = round(sum(r.get("proc_time") or 0 for r in history) / total, 1) if total else 0
    pct     = min(total / 700 * 100, 100)

    c1,c2,c3,c4 = st.columns(4)
    for col, val, lbl in [
        (c1, str(total),                    "Total approved"),
        (c2, f"{pct:.1f}%",                 "Phase 2 progress"),
        (c3, f"{avg_r}/5" if total else "—","Avg. quality"),
        (c4, f"{avg_t}s"  if total else "—","Avg. proc. time"),
    ]:
        col.markdown(
            f'<div class="kpi-box"><div class="kpi-value">{val}</div>'
            f'<div class="kpi-label">{lbl}</div></div>', unsafe_allow_html=True,
        )
    st.progress(pct / 100)
    st.caption(f"Fine-tuning threshold: 700 approved records  ({total} / 700)")
    st.divider()

    st.markdown(
        '<span class="header-accent"></span>'
        '<span style="font-weight:600;font-size:15px;">Development Roadmap</span>',
        unsafe_allow_html=True,
    )
    phases = [
        ("Phase 0","Mar 2026",     "done",   "Prototype Validation", ["Gemini API POC 완료","파이프라인 설계","EMR 보정 가능성 확인"]),
        ("Phase 1","Apr-Jun 2026","active",  "Data & Infrastructure",["IRB 승인","Annotation Dashboard 구축","EMR API 연동 설계"]),
        ("Phase 2","Jul-Sep 2026","pending", "Model Development",    ["온-프레미스 GPU 세팅","LLM Fine-tuning","요약 품질 고도화"]),
        ("Phase 3","Oct-Dec 2026","pending", "Clinical Validation",  ["300건+ 실증 검증","KPI 달성 확인","EMR API 완전 연동"]),
    ]
    cm = {"done":"#f0fdf4","active":"#eff6ff","pending":"#f8fafc"}
    bm = {"done":"#bbf7d0","active":"#bfdbfe","pending":"#e2e8f0"}
    tm = {"done":"#166534","active":"#1d4ed8","pending":"#94a3b8"}
    lm = {"done":"Complete","active":"In progress","pending":"Planned"}

    cols = st.columns(4)
    for col, (phase, period, status, title, items) in zip(cols, phases):
        ih = "".join(f'<li style="font-size:12px;color:#334155;margin-bottom:4px;">{i}</li>' for i in items)
        col.markdown(
            f'<div style="background:{cm[status]};border:1px solid {bm[status]};'
            f'border-radius:8px;padding:16px;min-height:180px;">'
            f'<div style="font-size:11px;font-weight:700;color:{tm[status]};margin-bottom:2px;">{phase} · {period}</div>'
            f'<div style="font-weight:600;font-size:13px;color:#0f172a;margin-bottom:6px;">{title}</div>'
            f'<span style="font-size:10px;font-weight:600;background:{cm[status]};color:{tm[status]};'
            f'padding:2px 8px;border-radius:4px;border:1px solid {bm[status]};">{lm[status]}</span>'
            f'<ul style="padding-left:14px;margin:10px 0 0;">{ih}</ul></div>',
            unsafe_allow_html=True,
        )
    st.divider()

    st.markdown(
        '<span class="header-accent"></span>'
        '<span style="font-weight:600;font-size:15px;">Approved Records</span>',
        unsafe_allow_html=True,
    )
    if not history:
        st.info("승인된 케이스가 없습니다. Case Review 탭에서 검수 후 승인하세요.")
    else:
        import pandas as pd
        df = pd.DataFrame([{
            "ID": r["id"], "Timestamp": r["timestamp"],
            "File": r["filename"], "Rating": f"{r['rating']}/5",
            "Proc.(s)": r.get("proc_time","-"),
        } for r in reversed(history)])
        st.dataframe(df, use_container_width=True, hide_index=True)

        all_json = json.dumps(history, ensure_ascii=False, indent=2)
        st.download_button(
            "전체 Ground Truth 다운로드 (JSON)", data=all_json,
            file_name=f"ground_truth_{datetime.now().strftime('%Y%m%d')}.json",
            mime="application/json",
        )
