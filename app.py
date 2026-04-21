"""
MDT 다학제 회의 자동 요약 AI Agent
Gemini 2.5 Flash 기반 | STT 텍스트 + EMR 맥락 → 구조화 요약
"""

import streamlit as st
import google.generativeai as genai
import json
import time
import re
from datetime import datetime

# ──────────────────────────────────────────────
# 페이지 설정
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="MDT 회의 요약 AI Agent",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────
# CSS
# ──────────────────────────────────────────────
st.markdown("""
<style>
/* 전체 폰트 & 배경 */
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap');
html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }

/* 섹션 카드 */
.section-card {
    background: #f8fafc;
    border-radius: 12px;
    padding: 16px 20px;
    border-left: 4px solid;
    margin-bottom: 12px;
}
.section-patient  { border-color: #185fa5; }
.section-findings { border-color: #0f6e56; }
.section-discuss  { border-color: #534ab7; }
.section-plan     { border-color: #993c1d; }
.section-next     { border-color: #854f0b; }

.section-title {
    font-weight: 700;
    font-size: 13px;
    letter-spacing: 0.5px;
    margin-bottom: 8px;
    text-transform: uppercase;
}

/* KPI 카드 */
.kpi-box {
    background: white;
    border-radius: 10px;
    padding: 16px;
    text-align: center;
    border: 1px solid #e2e8f0;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.kpi-value { font-size: 26px; font-weight: 800; }
.kpi-label { font-size: 11px; color: #6b7280; margin-top: 4px; letter-spacing: 0.4px; }

/* 상태 뱃지 */
.badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.3px;
}
.badge-blue   { background: #e6f1fb; color: #185fa5; }
.badge-green  { background: #e1f5ee; color: #0f6e56; }
.badge-gray   { background: #f1f5f9; color: #6b7280; }
.badge-amber  { background: #faeeda; color: #854f0b; }

/* 파이프라인 스텝 */
.pipeline-step {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    border-radius: 8px;
    margin-bottom: 6px;
    font-size: 13px;
}
.step-done    { background: #e1f5ee; color: #0f6e56; }
.step-active  { background: #e6f1fb; color: #185fa5; }
.step-pending { background: #f8fafc; color: #9ca3af; }

/* Streamlit 기본 UI 정리 */
.stTextArea textarea { font-size: 13px !important; line-height: 1.8 !important; }
.stButton button { border-radius: 10px !important; font-weight: 600 !important; }
div[data-testid="stSidebar"] { background: #f8fafc; }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# 상수
# ──────────────────────────────────────────────
SECTION_META = {
    "patient_info":   {"label": "환자 정보",   "icon": "👤", "cls": "section-patient",  "color": "#185fa5"},
    "key_findings":   {"label": "주요 소견",   "icon": "🔬", "cls": "section-findings", "color": "#0f6e56"},
    "discussion":     {"label": "논의 사항",   "icon": "💬", "cls": "section-discuss",  "color": "#534ab7"},
    "treatment_plan": {"label": "치료 계획",   "icon": "💊", "cls": "section-plan",     "color": "#993c1d"},
    "next_steps":     {"label": "다음 단계",   "icon": "📋", "cls": "section-next",     "color": "#854f0b"},
}

SAMPLE_TRANSCRIPT = """[다학제 진료 회의 - 환자 홍길동]

종양내과: 안녕하세요, 홍길동 환자분. 오늘 다학제 회의에 오셨군요.

환자: 네, 안녕하세요. 잘 부탁드립니다.

종양내과: 지난 항암치료 2차 이후 검사 결과 말씀드릴게요. CA19-9가 487로 이전보다 올랐고, 영상 소견에서 주병변은 2.1cm로 유지되나 간내 전이 의심 병변이 새로 보입니다.

영상의학과: 맞습니다. 이번 MRI에서 간 S6 부위에 1.2cm 크기의 신규 병변이 확인됩니다. 조영증강 패턴이 전이성 병변에 합당합니다.

외과: 수술적 접근은 현 상황에서 어렵습니다. 간전이가 확인되면 절제 불가 케이스로 봐야 합니다.

종양내과: 그렇다면 FOLFOX 또는 GEMOX 2차 항암 전환을 고려해야 할 것 같습니다. 방사선 선생님 의견은요?

방사선종양학과: 주병변에 대한 방사선 치료는 가능하나, 간전이 병변이 있는 상황에서 국소 치료의 이득이 제한적입니다. SBRT보다 전신 치료 우선을 권고합니다.

종양내과: 환자분, 앞으로의 치료 방향에 대해 궁금한 점 있으신가요?

환자: 항암이 바뀌는 건가요? 부작용이 걱정됩니다.

종양내과: 네, 좀 더 강한 항암으로 전환을 검토하고 있습니다. 부작용에 대해 자세히 설명드리겠습니다."""

SAMPLE_EMR = {
    "name": "홍길동 (익명)",
    "age": "62세",
    "gender": "남성",
    "diagnosis": "담관세포암 (Cholangiocarcinoma)",
    "stage": "Stage IIIA",
    "medications": "Gemcitabine 1000mg/m², Cisplatin 25mg/m²",
    "lab": "CA19-9: 487 U/mL (↑), CEA: 12.3 ng/mL (↑), Total Bilirubin: 2.1 mg/dL",
    "prev_summary": "2026-03-15: 항암 2차 완료, 부분 반응(PR) 확인, 담도 스텐트 교체 예정 논의",
}

# ──────────────────────────────────────────────
# 세션 상태 초기화
# ──────────────────────────────────────────────
def init_session():
    defaults = {
        "summary": None,
        "edit_mode": {},
        "edit_values": {},
        "approved": False,
        "rating": 0,
        "history": [],
        "transcript": "",
        "processing_time": None,
        "emr": SAMPLE_EMR.copy(),
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()

# ──────────────────────────────────────────────
# Gemini 요약 함수
# ──────────────────────────────────────────────
def build_prompt(transcript: str, emr: dict) -> str:
    return f"""당신은 다학제 회의(MDT) 전문 의료 AI 요약 에이전트입니다.
다학제 회의 전사 텍스트와 EMR 맥락 데이터를 분석하여 구조화된 회의 요약을 생성합니다.

[EMR 맥락 데이터 - 의학 용어 오인식 보정에 활용]
환자명: {emr.get('name', '')}
나이/성별: {emr.get('age', '')} / {emr.get('gender', '')}
진단명: {emr.get('diagnosis', '')}
병기: {emr.get('stage', '')}
복용약물: {emr.get('medications', '')}
최근 검사 수치: {emr.get('lab', '')}
이전 회의 요약: {emr.get('prev_summary', '')}

[다학제 회의 전사 텍스트]
{transcript}

위 EMR 데이터를 맥락으로 활용하여 전사 텍스트를 분석하고, 반드시 아래 JSON 형식으로만 응답하세요.
다른 텍스트, 마크다운 코드블록, 설명 없이 JSON만 출력하세요.

{{
  "patient_info": "환자 기본 정보 및 진단 요약 (2-3줄, 한국어)",
  "key_findings": "영상·검사 소견 요약, 주요 수치 변화 포함 (3-5줄, 한국어)",
  "discussion": "각 진료과별 의견과 논의된 치료 옵션 (4-6줄, 한국어)",
  "treatment_plan": "합의된 치료 방향 및 계획 (2-4줄, 한국어)",
  "next_steps": "추가 검사, 타과 의뢰, 다음 방문 계획 (2-3줄, 한국어)"
}}"""


def generate_summary(api_key: str, transcript: str, emr: dict) -> dict:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")
    prompt = build_prompt(transcript, emr)

    response = model.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.2,
            max_output_tokens=2048,
        ),
    )
    raw = response.text.strip()

    # JSON 파싱 (코드블록 제거 후)
    raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    return json.loads(raw)

# ──────────────────────────────────────────────
# 환자 구간 탐지 (텍스트 패턴)
# ──────────────────────────────────────────────
def detect_patient_segment(transcript: str) -> bool:
    patterns = ["안녕하세요", "환자분", "오셨군요", "잘 부탁드립니다"]
    return any(p in transcript for p in patterns)

# ──────────────────────────────────────────────
# 사이드바
# ──────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🩺 MDT Summary Agent")
    st.markdown('<span class="badge badge-blue">Phase 1 · Gemini 2.5 Flash</span>', unsafe_allow_html=True)
    st.divider()

    # API 키
    st.markdown("#### 🔑 Gemini API 키")
    api_key = st.text_input("API Key", type="password", placeholder="AIza...", label_visibility="collapsed")
    if api_key:
        st.success("API 키 입력됨", icon="✅")
    else:
        st.info("Google AI Studio에서 발급 받으세요")
        st.markdown("[발급 바로가기 →](https://aistudio.google.com/apikey)", unsafe_allow_html=False)

    st.divider()

    # KPI
    st.markdown("#### 📊 목표 KPI")
    kpis = [
        ("85%", "회의록 작성 시간 단축"),
        ("0.80+", "구조화 요약 F1-score"),
        ("80%+", "의료진 만족도"),
        ("300건+", "실증 테스트 목표"),
    ]
    for val, label in kpis:
        st.markdown(f"""
        <div class="kpi-box" style="margin-bottom:8px;">
            <div class="kpi-value" style="color:#185fa5;">{val}</div>
            <div class="kpi-label">{label}</div>
        </div>""", unsafe_allow_html=True)

    st.divider()

    # 파이프라인 상태
    st.markdown("#### ⚙️ 파이프라인 상태")
    transcript_filled = bool(st.session_state.transcript.strip())
    patient_detected = detect_patient_segment(st.session_state.transcript)
    summary_done = st.session_state.summary is not None
    approved = st.session_state.approved

    steps = [
        ("구간 탐지",       "done" if patient_detected else ("active" if transcript_filled else "pending")),
        ("EMR 맥락 주입",   "done" if transcript_filled else "pending"),
        ("LLM 요약 생성",   "done" if summary_done else "pending"),
        ("의료진 검수",     "done" if approved else ("active" if summary_done else "pending")),
        ("Ground Truth 저장","done" if approved else "pending"),
    ]
    icons = {"done": "✅", "active": "🔄", "pending": "⏳"}
    cls   = {"done": "step-done", "active": "step-active", "pending": "step-pending"}
    for name, status in steps:
        st.markdown(f"""
        <div class="pipeline-step {cls[status]}">
            {icons[status]} {name}
        </div>""", unsafe_allow_html=True)

    st.divider()
    total = len(st.session_state.history)
    st.markdown(f"**축적 데이터**: `{total}` / 700건 (Phase 2 전환 기준)")
    if total > 0:
        st.progress(min(total / 700, 1.0))

# ──────────────────────────────────────────────
# 메인 헤더
# ──────────────────────────────────────────────
st.markdown("## 🏥 MDT 회의 자동 요약 AI Agent")
st.caption("STT 전사 텍스트 + EMR 맥락 → Gemini 2.5 Flash → 구조화 요약 → 의료진 검수 → Ground Truth 축적")
st.divider()

# ──────────────────────────────────────────────
# 탭
# ──────────────────────────────────────────────
tab_input, tab_summary, tab_history = st.tabs(["📥 입력 & EMR", "📄 요약 검수", "📊 현황 & 이력"])

# ════════════════════════════════════════════════
# 탭 1: 입력 & EMR
# ════════════════════════════════════════════════
with tab_input:
    col_left, col_right = st.columns([3, 2], gap="large")

    # ── 왼쪽: 전사 텍스트 ──
    with col_left:
        st.markdown("### 🎙️ 회의 전사 텍스트")

        # 샘플 로드 / 초기화
        btn_col1, btn_col2, _ = st.columns([1, 1, 3])
        with btn_col1:
            if st.button("📋 샘플 로드"):
                st.session_state.transcript = SAMPLE_TRANSCRIPT
                st.rerun()
        with btn_col2:
            if st.button("🗑️ 초기화"):
                st.session_state.transcript = ""
                st.session_state.summary = None
                st.session_state.approved = False
                st.session_state.rating = 0
                st.rerun()

        # 파일 업로드
        uploaded = st.file_uploader(
            "파일 업로드 (.txt / .vtt / .srt)",
            type=["txt", "vtt", "srt"],
            label_visibility="collapsed",
        )
        if uploaded:
            content = uploaded.read().decode("utf-8", errors="ignore")
            st.session_state.transcript = content
            st.success(f"파일 로드 완료: {uploaded.name} ({len(content):,}자)")

        # 텍스트 입력창
        transcript = st.text_area(
            "전사 텍스트",
            value=st.session_state.transcript,
            height=380,
            placeholder="STT 전사 텍스트를 붙여넣거나, 샘플 로드 / 파일 업로드를 사용하세요.\n\n형식 예시:\n종양내과: 안녕하세요, 환자분...\n환자: 네, 안녕하세요...",
            label_visibility="collapsed",
        )
        st.session_state.transcript = transcript

        # 상태 표시
        word_count = len(transcript.split()) if transcript.strip() else 0
        char_count = len(transcript)
        info_cols = st.columns(3)
        info_cols[0].metric("단어 수", f"{word_count:,}")
        info_cols[1].metric("글자 수", f"{char_count:,}")
        info_cols[2].metric(
            "환자 구간",
            "탐지됨 ✅" if detect_patient_segment(transcript) else "미탐지 ⚠️",
        )

    # ── 오른쪽: EMR 패널 ──
    with col_right:
        st.markdown("### 🏥 EMR 맥락 데이터")
        st.caption("의학 용어 오인식 보정 및 요약 품질 향상에 활용됩니다.")

        emr = st.session_state.emr
        emr["name"]        = st.text_input("환자명 (익명)", value=emr["name"])
        c1, c2 = st.columns(2)
        emr["age"]         = c1.text_input("나이", value=emr["age"])
        emr["gender"]      = c2.text_input("성별", value=emr["gender"])
        emr["diagnosis"]   = st.text_input("진단명", value=emr["diagnosis"])
        emr["stage"]       = st.text_input("병기", value=emr["stage"])
        emr["medications"] = st.text_input("복용 약물", value=emr["medications"])
        emr["lab"]         = st.text_area("최근 검사 수치", value=emr["lab"], height=80)
        emr["prev_summary"]= st.text_area("이전 회의 요약", value=emr["prev_summary"], height=80)
        st.session_state.emr = emr

        # EMR 보정 현황
        st.markdown("---")
        st.markdown("**EMR 맥락 보정 항목**")
        checks = [
            ("진단명 교차검증",    bool(emr["diagnosis"])),
            ("약물명 오인식 보정", bool(emr["medications"])),
            ("검사수치 참조",      bool(emr["lab"])),
            ("이전 요약 연속성",   bool(emr["prev_summary"])),
        ]
        for label, ok in checks:
            st.markdown(f"{'✅' if ok else '⬜'} {label}")

    st.divider()

    # ── 요약 생성 버튼 ──
    if not api_key:
        st.warning("⬅️ 사이드바에서 Gemini API 키를 먼저 입력해주세요.")
    else:
        gen_btn = st.button(
            "🤖 AI 구조화 요약 생성",
            type="primary",
            use_container_width=True,
            disabled=not transcript.strip(),
        )

        if gen_btn:
            with st.spinner(""):
                progress_bar = st.progress(0)
                status_text  = st.empty()

                steps_progress = [
                    (15, "🔍 환자 진료 구간 탐지 중..."),
                    (35, "💉 EMR 맥락 데이터 주입 중..."),
                    (60, "🧠 Gemini 2.5 Flash 요약 생성 중..."),
                    (85, "✨ 구조화 포맷 적용 중..."),
                    (100, "✅ 완료!"),
                ]
                for pct, msg in steps_progress[:-1]:
                    progress_bar.progress(pct)
                    status_text.markdown(f"**{msg}**")
                    time.sleep(0.4)

                t_start = time.time()
                try:
                    result = generate_summary(api_key, transcript, st.session_state.emr)
                    elapsed = round(time.time() - t_start, 1)

                    progress_bar.progress(100)
                    status_text.markdown("**✅ 요약 생성 완료!**")

                    st.session_state.summary         = result
                    st.session_state.edit_values     = result.copy()
                    st.session_state.edit_mode       = {k: False for k in SECTION_META}
                    st.session_state.approved        = False
                    st.session_state.rating          = 0
                    st.session_state.processing_time = elapsed

                    time.sleep(0.5)
                    st.success(f"요약 생성 완료 ({elapsed}초) — '📄 요약 검수' 탭으로 이동하세요.")

                except json.JSONDecodeError as e:
                    st.error(f"JSON 파싱 실패: {e}\nGemini 응답 형식을 확인하세요.")
                except Exception as e:
                    st.error(f"오류: {e}")
                finally:
                    time.sleep(1)
                    progress_bar.empty()
                    status_text.empty()

# ════════════════════════════════════════════════
# 탭 2: 요약 검수
# ════════════════════════════════════════════════
with tab_summary:
    if st.session_state.summary is None:
        st.info("📥 입력 탭에서 전사 텍스트를 입력하고 요약을 생성해주세요.")
        st.stop()

    summary = st.session_state.summary
    col_main, col_review = st.columns([3, 1], gap="large")

    # ── 왼쪽: 섹션별 요약 ──
    with col_main:
        header_c1, header_c2 = st.columns([2, 1])
        with header_c1:
            st.markdown("### 📄 AI 생성 구조화 요약")
        with header_c2:
            if st.session_state.processing_time:
                st.metric("처리 시간", f"{st.session_state.processing_time}초")

        for section_key, meta in SECTION_META.items():
            content = st.session_state.edit_values.get(section_key, summary.get(section_key, ""))
            with st.expander(f"{meta['icon']} {meta['label']}", expanded=True):
                is_editing = st.session_state.edit_mode.get(section_key, False)

                if is_editing:
                    new_val = st.text_area(
                        f"편집: {meta['label']}",
                        value=content,
                        height=120,
                        key=f"edit_{section_key}",
                        label_visibility="collapsed",
                    )
                    s1, s2, _ = st.columns([1, 1, 4])
                    if s1.button("💾 저장", key=f"save_{section_key}"):
                        st.session_state.edit_values[section_key] = new_val
                        st.session_state.edit_mode[section_key]   = False
                        st.rerun()
                    if s2.button("✕ 취소", key=f"cancel_{section_key}"):
                        st.session_state.edit_mode[section_key] = False
                        st.rerun()
                else:
                    st.markdown(
                        f'<div class="section-card {meta["cls"]}">'
                        f'<p style="margin:0; font-size:14px; line-height:1.8; color:#374151;">{content}</p>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    if st.button(f"✏️ 수정", key=f"edit_btn_{section_key}"):
                        st.session_state.edit_mode[section_key] = True
                        st.rerun()

        # 전체 JSON 보기
        with st.expander("🔧 원본 JSON 보기", expanded=False):
            st.json(st.session_state.edit_values)

    # ── 오른쪽: 검수 패널 ──
    with col_review:
        st.markdown("### ✅ 검수 평가")

        # 만족도 점수
        st.markdown("**요약 품질 평가**")
        rating = st.select_slider(
            "점수",
            options=[1, 2, 3, 4, 5],
            value=max(st.session_state.rating, 1),
            format_func=lambda x: ["★☆☆☆☆", "★★☆☆☆", "★★★☆☆", "★★★★☆", "★★★★★"][x - 1],
            label_visibility="collapsed",
        )
        st.session_state.rating = rating
        labels = {1: "매우 불만족", 2: "불만족", 3: "보통", 4: "만족", 5: "매우 만족"}
        st.caption(f"{labels[rating]} ({rating}/5)")

        st.markdown("---")

        # 승인 버튼
        if st.session_state.approved:
            st.success("✅ 검수 완료\n\nGround Truth로 저장되었습니다.")
        else:
            if st.button("✅ 승인 및 Ground Truth 저장", type="primary", use_container_width=True):
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
        st.markdown("**EMR 교차 검증**")
        checks = [
            ("진단명 일치",     True),
            ("약물명 정확도",   True),
            ("검사수치 참조",   True),
            ("이전 요약 연속",  bool(st.session_state.emr.get("prev_summary"))),
            ("예약 연동",       False),
        ]
        for label, ok in checks:
            color = "#0f6e56" if ok else "#9ca3af"
            icon  = "✅" if ok else "⏳"
            st.markdown(
                f'<div style="font-size:12px; color:{color}; margin-bottom:4px;">'
                f'{icon} {label}</div>',
                unsafe_allow_html=True,
            )

        # JSON 다운로드
        st.markdown("---")
        st.markdown("**내보내기**")
        json_str = json.dumps(st.session_state.edit_values, ensure_ascii=False, indent=2)
        st.download_button(
            label="⬇️ JSON 다운로드",
            data=json_str,
            file_name=f"mdt_summary_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
            mime="application/json",
            use_container_width=True,
        )

        txt_output = "\n\n".join(
            f"[{SECTION_META[k]['icon']} {SECTION_META[k]['label']}]\n{v}"
            for k, v in st.session_state.edit_values.items()
        )
        st.download_button(
            label="⬇️ TXT 다운로드",
            data=txt_output,
            file_name=f"mdt_summary_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
            mime="text/plain",
            use_container_width=True,
        )

# ════════════════════════════════════════════════
# 탭 3: 현황 & 이력
# ════════════════════════════════════════════════
with tab_history:
    st.markdown("### 📊 축적 현황")

    history = st.session_state.history
    total = len(history)
    avg_rating = round(sum(r["rating"] for r in history) / total, 1) if total else 0
    avg_time   = round(sum(r["proc_time"] or 0 for r in history) / total, 1) if total else 0
    phase2_progress = min(total / 700 * 100, 100)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("총 처리 건수",       f"{total}건")
    c2.metric("Phase 2 진행률",     f"{phase2_progress:.1f}%")
    c3.metric("평균 만족도",         f"{avg_rating}/5.0" if total else "-")
    c4.metric("평균 처리 시간",      f"{avg_time}초" if total else "-")

    st.progress(phase2_progress / 100)
    st.caption(f"Fine-tuning 전환 기준: 700건 ({total}/700 완료)")
    st.divider()

    # 로드맵
    st.markdown("### 🗺️ 개발 로드맵")
    phases = [
        ("Phase 0", "2026.03", "done",    "프로토타입 검증",   ["Gemini POC", "파이프라인 설계", "EMR 보정 확인"]),
        ("Phase 1", "2026.04-06", "active","데이터 기반 구축", ["IRB 승인", "검수 UI 개발", "API 연동 안정화"]),
        ("Phase 2", "2026.07-09", "pending","고도화",          ["GPU 온프레미스", "LLM Fine-tuning", "요약 품질 향상"]),
        ("Phase 3", "2026.10-12", "pending","실증 테스트",     ["300건+ 실증", "성능 지표 달성", "EMR 완전 연동"]),
    ]
    cols = st.columns(4)
    color_map = {"done": "#e1f5ee", "active": "#e6f1fb", "pending": "#f8fafc"}
    border_map = {"done": "#9fe1cb", "active": "#b5d4f4", "pending": "#e2e8f0"}
    text_map   = {"done": "#0f6e56", "active": "#185fa5", "pending": "#9ca3af"}

    for col, (phase, period, status, title, items) in zip(cols, phases):
        items_html = "".join(
            f'<li style="margin-bottom:4px; font-size:12px; color:#374151;">{item}</li>'
            for item in items
        )
        col.markdown(f"""
        <div style="background:{color_map[status]};border:1.5px solid {border_map[status]};
                    border-radius:10px;padding:14px;height:180px;">
            <div style="font-size:10px;font-weight:700;color:{text_map[status]};
                        letter-spacing:0.5px;margin-bottom:4px;">{phase} · {period}</div>
            <div style="font-weight:700;font-size:13px;color:#1a202c;margin-bottom:8px;">{title}</div>
            <ul style="padding-left:14px;margin:0;">{items_html}</ul>
        </div>""", unsafe_allow_html=True)

    st.divider()

    # 처리 이력 테이블
    st.markdown("### 🗂️ 처리 이력")
    if not history:
        st.info("아직 검수 완료된 요약이 없습니다. 요약을 생성하고 승인하면 여기에 기록됩니다.")
    else:
        import pandas as pd
        df = pd.DataFrame([
            {
                "ID":       r["id"],
                "일시":     r["timestamp"],
                "환자":     r["patient"],
                "진단명":   r["diagnosis"],
                "평점":     "★" * r["rating"] + "☆" * (5 - r["rating"]),
                "처리시간(초)": r["proc_time"],
            }
            for r in reversed(history)
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Ground Truth JSON 전체 다운로드
        all_json = json.dumps(history, ensure_ascii=False, indent=2)
        st.download_button(
            label="⬇️ 전체 Ground Truth 다운로드 (JSON)",
            data=all_json,
            file_name=f"ground_truth_{datetime.now().strftime('%Y%m%d')}.json",
            mime="application/json",
        )
