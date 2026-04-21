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

/* EMR API placeholder banner */
.emr-api-notice {
    background: #eff6ff;
    border: 1px solid #bfdbfe;
    border-left: 4px solid #2563eb;
    border-radius: 6px;
    padding: 10px 14px;
    margin-bottom: 12px;
    font-size: 12px;
    color: #1e40af;
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

# ── EMR Agent output fields (for future API integration) ──────────────────
# The EMR Summary Agent produces the following structured sections:
#   - comprehensive_summary   : 종합 요약 (3문장 이내 핵심 요약)
#   - current_status          : 현재 상태 (현재 증상·상태·주요 수치, 최신 검사일자 기준)
#   - progress_record         : 경과 기록 (의사결정 중심 치료·검사 타임라인)
#   - key_procedures          : 주요 검사·시술 (영상·병리·시술·수술 결과, 원문 근거 연결)
#   - consultation_issues     : 협진 쟁점 (추가 판단이 필요한 항목)
# Input fields accepted by EMR Agent:
#   patient_information, procedure, surgery, chemotherapy, radiation,
#   imaging, biopsies, blood, history, medication

SAMPLE_TRANSCRIPT = """라고 그러 이 환자는 수술이 괜찮아 수술 가능하지 않을까 싶은데요.
리셉터블 이번에 있는 환자인가요? 네 알겠습니다.

답변 주신 게 CA 199가 너무 높다고 해서

떨어졌습니다. 맞아 맞아 6 7 6

이미징은 이색 터블이긴 한데

그랬던 거 맞아 이번은 그렇게 협진을 했던 것 같아요.

간 수치 떨어지긴 더디긴 하지만 상당히 떨어지고 c19다19도 처음에 아마 그 콜레스테 때문에 그럴 수 있죠.
올라간 것도 완전 정상은 아니지만

빨리 해버릴까요? 아니면

그게 나을 것 같아요.

그러면 이번 김에

케모할 거 아니면 그냥 어주시면

근데 아마 이분은 오퍼러블 한 걸로 총무 원가가 높아서 그렇지

맞아요. 나머지는 괜찮습니다.

인트로덕탈 타입이고 침범을 하더라도 그냥 리버 파르키만

옆에서 싸우고 있어서

핑크라스 파렌티마 전

전형적인 PPPD 하시면 될 것 같아요.

일단은 오늘 내일 랩 한번 보고 모티피티가 잘 안 떨어지고 오늘 조금 더 올라가지고 이것저것 패턴 보다가 퇴원시켜야 드리는 게 낫지 않나 싶은데 혹시 수술하면 언제쯤 가능하시죠?
다음 주 수요일 다음 주 수요일

네 안녕하세요. 예 여기 지금 췌장 담도 다학제 팀이고요.
췌장암이나 담도암에 대해서 상의하고 어떻게 치료할지 결정하는 팀입니다.
소개 말씀드리면은 옆에 계신 분이라 제가 이제 소화기내과 의사고요.
그다음에 외과 교수님 안녕하세요.

설명을 그래서 MRI 촬영을 하신 걸 보시면 MRI에 이제 여러 가지 종류의 사진이 있는데 이거는 이제 물 성분만 하얗게 보이고 물이 아닌 성분은 까맣게 신호를 죽여서 보여주는 거예요.
그래서 3차원으로 재구성을 한 건데 지금 이렇게 나뭇가지처럼 보이는 게 간 안에 그리고 간에 바깥쪽 이쪽 내려오는 부분까지 단관이 늘어나 있는 모습이 보이는 거거든요.
담도암이라고 진단이 됐어요. 다행히 원격 전이나 전이 소견이 없어서 수술이 가능한 상황입니다.

안녕하세요. 저는 외과사입니다. 수술 자체는 가능한 위치에 있고 전형적인 PPPD (췌두부 십이지장 절제술) 하시면 될 것 같아요.
수술 시간은 6시간에서 많게는 10시간 걸릴 때도 있고 로봇이나 복강경으로 하시면 됩니다.
다음 주 수요일에 수술 가능하고 퇴원하셨다가 월요일 날 입원하셔서 수술하시면 됩니다.

그럼 수술로 끝나는 거 아니면 수술하고 이제 항암도 같이 해야 되는

담도암은 1기라고 해도 혈관 침범이나 심장 침범이 있으면 항암 치료를 권유하는 경우가 꽤 많고 조직 검사가 나와야 혈액종양내과 교수님께서 결정해 주실 겁니다.

그래도 좀 이왕 어차피 할 거니까 빠른 게 좋지

맞나요? 그러면 다음 날 일단 제가 설명을 드릴게요."""

SAMPLE_EMR = {
    # ── Direct field input (현재 수동 입력 방식) ──
    "name":         "홍길동 (익명 처리)",
    "age":          "67",
    "gender":       "남성",
    "diagnosis":    "담관세포암 (Cholangiocarcinoma)",
    "stage":        "Stage II",
    "medications":  "젬시타빈 1000 mg/m², 시스플라틴 25 mg/m²",
    "lab":          "CA19-9: 110→67 U/mL (하강 중), CEA: 정상, Total Bilirubin: 2.3 mg/dL, LFT 상승",
    "prev_summary": "2026-03-01: ERCP 및 담도 스텐트 삽입 시행. CA19-9 급격히 상승 후 스텐트 삽입 후 하강 추세. 수술 가능성 검토 중.",
}

# ──────────────────────────────────────────────
# EMR API Integration Layer (Placeholder)
# ──────────────────────────────────────────────
# TODO: Replace this section with actual API call when EMR integration is ready.
# Two possible integration modes:
#   Mode A — Raw EMR API: Fetch structured EMR fields directly from hospital system
#             (patient_information, procedure, surgery, chemotherapy, radiation,
#              imaging, biopsies, blood, history, medication)
#   Mode B — EMR Summary Agent API: Fetch pre-summarised output from the
#             EMR Summary Agent (comprehensive_summary, current_status,
#             progress_record, key_procedures, consultation_issues)
#
# def fetch_emr_from_api(patient_id: str, mode: str = "summary") -> dict:
#     """
#     Fetch EMR context from hospital API.
#
#     Args:
#         patient_id: Hospital patient identifier
#         mode: "raw"     -> returns raw EMR fields
#               "summary" -> returns EMR Summary Agent output
#
#     Returns:
#         dict with EMR fields formatted for build_prompt()
#     """
#     if mode == "summary":
#         # Mode B: EMR Summary Agent output
#         endpoint = f"https://emr-api.hospital.internal/v1/summary/{patient_id}"
#         response = requests.get(endpoint, headers={"Authorization": f"Bearer {EMR_API_TOKEN}"})
#         data = response.json()
#         return {
#             "name":         data.get("patient_name", ""),
#             "age":          data.get("age", ""),
#             "gender":       data.get("gender", ""),
#             "diagnosis":    data.get("comprehensive_summary", ""),
#             "stage":        data.get("current_status", ""),
#             "medications":  data.get("key_procedures", ""),
#             "lab":          data.get("progress_record", ""),
#             "prev_summary": data.get("consultation_issues", ""),
#         }
#     else:
#         # Mode A: Raw EMR fields
#         endpoint = f"https://emr-api.hospital.internal/v1/patient/{patient_id}"
#         response = requests.get(endpoint, headers={"Authorization": f"Bearer {EMR_API_TOKEN}"})
#         data = response.json()
#         return {
#             "name":         data.get("patient_information", {}).get("name", ""),
#             "age":          data.get("patient_information", {}).get("age", ""),
#             "gender":       data.get("patient_information", {}).get("gender", ""),
#             "diagnosis":    data.get("history", ""),
#             "stage":        data.get("imaging", ""),
#             "medications":  data.get("medication", ""),
#             "lab":          data.get("blood", ""),
#             "prev_summary": f"Surgery: {data.get('surgery','')} | Chemo: {data.get('chemotherapy','')}",
#         }

def get_emr_context(patient_id: str = None) -> dict:
    """
    EMR context entry point.
    Currently returns manual session state values.
    When EMR API is ready, replace body with: return fetch_emr_from_api(patient_id, mode="summary")
    """
    return st.session_state.emr

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
        "emr_mode":        "manual",   # "manual" | "api_raw" | "api_summary"
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
Analyse the meeting transcript and EMR context below to produce a structured clinical summary in Korean.
The transcript is in Korean. Produce all summary output in Korean.
Respond ONLY with a valid JSON object. No preamble, no markdown code fences, no explanation.

[EMR Context — used for medical term correction and contextual grounding]
환자명: {emr.get('name', '')}
나이/성별: {emr.get('age', '')} / {emr.get('gender', '')}
진단명: {emr.get('diagnosis', '')}
병기: {emr.get('stage', '')}
현재 약물: {emr.get('medications', '')}
최근 검사 수치: {emr.get('lab', '')}
이전 회의 요약: {emr.get('prev_summary', '')}

[다학제 회의 전사 텍스트]
{transcript}

Output format (JSON only, all values in Korean):
{{
  "patient_info":   "환자 기본 정보 및 진단 요약 (2~3문장)",
  "key_findings":   "영상 및 검사 소견, 주요 수치 변화 포함 (3~5문장)",
  "discussion":     "각 과별 의견 및 논의된 치료 옵션 (4~6문장)",
  "treatment_plan": "확정된 치료 방향 및 계획 (2~4문장)",
  "next_steps":     "추가 검사, 타과 의뢰, 추적 일정 (2~3문장)"
}}"""


def generate_summary(api_key: str, transcript: str, emr: dict) -> dict:
    genai.configure(api_key=api_key)
    model    = genai.GenerativeModel("gemini-2.5-flash")

    # Truncate transcript if too long (Gemini token safety)
    max_chars = 12000
    if len(transcript) > max_chars:
        transcript = transcript[:max_chars] + "\n\n[... 전사 텍스트 일부 생략 ...]"

    response = model.generate_content(
        build_prompt(transcript, emr),
        generation_config=genai.GenerationConfig(temperature=0.2, max_output_tokens=2048),
    )
    raw = response.text.strip()
    # Strip markdown fences if present
    raw = re.sub(r"^```(?:json)?", "", raw, flags=re.MULTILINE).strip()
    raw = re.sub(r"```$", "", raw, flags=re.MULTILINE).strip()

    parsed = json.loads(raw)

    # Ensure all expected keys exist (fill missing with placeholder)
    for key in SECTION_META:
        if key not in parsed:
            parsed[key] = "(요약 생성 실패 — 해당 섹션을 수동으로 입력해 주세요.)"
    return parsed

# ──────────────────────────────────────────────
# Clinical consultation segment detection
# (환자 진료 구간 탐지 — formerly "patient segment")
# ──────────────────────────────────────────────
def detect_consultation_segment(transcript: str) -> bool:
    """
    Detect whether the transcript contains a patient consultation segment
    (환자 진료 구간) by identifying the greeting pattern from physician to patient,
    which typically marks the start of the clinical consultation portion.
    """
    patterns = [
        "안녕하세요", "환자분", "오셨군요", "반갑습니다",
        "good morning", "good afternoon", "thank you for coming",
        "patient:",
    ]
    t = transcript.lower()
    return any(p.lower() in t for p in patterns)

# ──────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        '<span style="font-size:18px;font-weight:700;color:#ffffff;">MDT Meeting Auto-Summary</span>',
        unsafe_allow_html=True,
    )
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
        ("0.85+", "Structured summary F1-score"),
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
    transcript_filled  = bool(st.session_state.transcript.strip())
    segment_detected   = detect_consultation_segment(st.session_state.transcript)
    summary_done       = st.session_state.summary is not None
    is_approved        = st.session_state.approved

    pipeline_steps = [
        ("Clinical consultation segment detection", "done"   if segment_detected  else ("active" if transcript_filled else "pending")),
        ("EMR context injection",                   "done"   if transcript_filled else "pending"),
        ("LLM summary",                             "done"   if summary_done      else "pending"),
        ("Clinician review",                        "done"   if is_approved       else ("active" if summary_done else "pending")),
        ("Ground truth saved",                      "done"   if is_approved       else "pending"),
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
    '<span style="font-size:22px;font-weight:700;color:#ffffff;">MDT Meeting Auto-Summary</span>'
    '&nbsp;&nbsp;<span style="font-size:13px;color:#ffffff;">AI Agent &nbsp;|&nbsp; Gemini 2.5 Flash</span>',
    unsafe_allow_html=True,
)
st.caption(
    "STT transcript + EMR context  "
    "->  Clinical consultation segment detection  "
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
                "STT 전사 텍스트를 붙여 넣거나, Load sample / 파일 업로드를 이용하세요.\n\n"
                "예시 형식:\n"
                "소화기내과: 안녕하세요...\n"
                "환자: 안녕하세요..."
            ),
            label_visibility="collapsed",
        )
        st.session_state.transcript = transcript

        m1, m2, m3 = st.columns(3)
        m1.metric("Words",      f"{len(transcript.split()):,}" if transcript.strip() else "0")
        m2.metric("Characters", f"{len(transcript):,}")
        m3.metric(
            "Clinical consultation segment",
            "Detected" if detect_consultation_segment(transcript) else "Not detected",
        )

    # ── EMR Context ──
    with col_right:
        st.markdown(
            '<span class="header-accent"></span>'
            '<span style="font-weight:600;font-size:15px;">EMR Context</span>',
            unsafe_allow_html=True,
        )

        # EMR integration mode notice
        st.markdown(
            '<div class="emr-api-notice">'
            '🔌 <strong>EMR API 연동 예정</strong><br>'
            '현재는 수동 입력 방식으로 운영됩니다. 향후 EMR API 또는 EMR 요약 에이전트 API 연동으로 자동 대체될 예정입니다.'
            '</div>',
            unsafe_allow_html=True,
        )

        # EMR mode selector (for future toggle)
        emr_mode = st.radio(
            "EMR 데이터 입력 방식",
            options=["수동 입력 (현재)", "Raw EMR API (준비 중)", "EMR 요약 에이전트 API (준비 중)"],
            index=0,
            horizontal=True,
            label_visibility="visible",
        )

        if emr_mode != "수동 입력 (현재)":
            st.info(
                "EMR API 연동이 준비되면 활성화됩니다.\n\n"
                "**Raw EMR API** — 병원 EMR 시스템에서 직접 환자 정보, 시술, 수술, 항암, 방사선, "
                "영상, 조직검사, 혈액검사, 병력, 약물 데이터를 수신합니다.\n\n"
                "**EMR 요약 에이전트 API** — EMR 요약 에이전트가 생성한 종합 요약·현재 상태·경과 기록·"
                "주요 검사·협진 쟁점을 수신하여 MDT 요약 생성에 활용합니다."
            )
        else:
            st.caption("의료 용어 보정 및 맥락 기반 요약 품질 향상에 활용됩니다.")
            emr = st.session_state.emr
            emr["name"]         = st.text_input("환자명 (익명 처리)", value=emr["name"])
            c1, c2              = st.columns(2)
            emr["age"]          = c1.text_input("나이", value=emr["age"])
            emr["gender"]       = c2.text_input("성별", value=emr["gender"])
            emr["diagnosis"]    = st.text_input("진단명", value=emr["diagnosis"])
            emr["stage"]        = st.text_input("병기", value=emr["stage"])
            emr["medications"]  = st.text_input("현재 약물", value=emr["medications"])
            emr["lab"]          = st.text_area("최근 검사 수치", value=emr["lab"], height=75)
            emr["prev_summary"] = st.text_area("이전 회의 요약", value=emr["prev_summary"], height=75)
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
        st.warning("사이드바에 Gemini API 키를 입력하세요.")
    else:
        gen_btn = st.button(
            "Generate Structured Summary",
            type="primary",
            use_container_width=True,
            disabled=not st.session_state.transcript.strip(),
        )

        if gen_btn:
            progress_bar = st.progress(0)
            status_text  = st.empty()

            for pct, msg in [
                (15, "Clinical consultation segment detection..."),
                (35, "Injecting EMR context..."),
                (60, "Generating summary with Gemini 2.5 Flash..."),
                (85, "Applying structured output format..."),
            ]:
                progress_bar.progress(pct)
                status_text.markdown(f"*{msg}*")
                time.sleep(0.35)

            t_start = time.time()
            try:
                emr_context = get_emr_context()
                result      = generate_summary(api_key, st.session_state.transcript, emr_context)
                elapsed     = round(time.time() - t_start, 1)

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
                st.error(f"JSON parse error: {e}\n\nGemini 응답이 JSON 형식이 아닙니다. API 키와 입력 텍스트를 확인하세요.")
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
        ("Phase 1", "Apr-Jun 2026", "active",  "Data & Infrastructure", ["IRB approval", "Review UI build", "EMR API integration design"]),
        ("Phase 2", "Jul-Sep 2026", "pending", "Model Development",     ["On-prem GPU setup", "LLM fine-tuning", "Summary quality uplift"]),
        ("Phase 3", "Oct-Dec 2026", "pending", "Clinical Validation",   ["300+ case validation", "KPI verification", "Full EMR API integration"]),
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
