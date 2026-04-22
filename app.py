"""
MDT Meeting Auto-Summary — Clinical Annotation Dashboard
Streamlit frontend  ↔  FastAPI backend (server.py)
"""

import streamlit as st
import requests, json, time
from datetime import datetime

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────
API_BASE = "http://localhost:8000"

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
html,body,[class*="css"]{font-family:'Inter',sans-serif;}

.section-card{background:#f8fafc;border-radius:8px;padding:14px 18px;
  border-left:3px solid;margin-bottom:8px;}
.sc-patient {border-color:#2563eb;} .sc-findings{border-color:#059669;}
.sc-discuss {border-color:#7c3aed;} .sc-plan    {border-color:#b45309;}
.sc-next    {border-color:#0891b2;}

.badge{display:inline-block;padding:2px 9px;border-radius:4px;
  font-size:11px;font-weight:600;letter-spacing:.2px;}
.b-approved{background:#f0fdf4;color:#166534;border:1px solid #bbf7d0;}
.b-generated{background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;}
.b-pending{background:#fef9c3;color:#854d0e;border:1px solid #fde68a;}

.case-row{padding:10px 14px;border-radius:8px;border:1px solid #e2e8f0;
  margin-bottom:6px;background:#fff;}
.case-row-sel{border-color:#2563eb;background:#eff6ff;}

.transcript-box{background:#1e293b;border-radius:8px;padding:14px 16px;
  font-size:12.5px;line-height:1.85;color:#e2e8f0;white-space:pre-wrap;
  max-height:480px;overflow-y:auto;font-family:monospace;}

.kpi-box{background:#fff;border-radius:8px;padding:14px 16px;
  text-align:center;border:1px solid #e2e8f0;}
.kpi-value{font-size:22px;font-weight:700;color:#1e40af;}
.kpi-label{font-size:11px;color:#64748b;margin-top:3px;}

.pipe-step{display:flex;align-items:center;gap:8px;padding:7px 10px;
  border-radius:6px;margin-bottom:5px;font-size:12px;font-weight:500;}
.ps-done   {background:#f0fdf4;color:#166534;border:1px solid #bbf7d0;}
.ps-active {background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;}
.ps-pending{background:#f8fafc;color:#94a3b8;border:1px solid #e2e8f0;}
.pd{width:7px;height:7px;border-radius:50%;flex-shrink:0;}
.pd-done{background:#16a34a;} .pd-active{background:#2563eb;} .pd-pending{background:#cbd5e1;}

.ha{display:inline-block;width:3px;height:16px;background:#2563eb;
  border-radius:2px;margin-right:8px;vertical-align:middle;}
.emr-notice{background:#eff6ff;border:1px solid #bfdbfe;border-left:4px solid #2563eb;
  border-radius:6px;padding:10px 14px;margin-bottom:10px;font-size:12px;color:#1e40af;line-height:1.6;}

.stTextArea textarea{font-size:13px!important;line-height:1.75!important;}
.stButton>button{border-radius:6px!important;font-weight:500!important;}
div[data-testid="stSidebar"]{background:#f8fafc;border-right:1px solid #e2e8f0;}
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────
SECTION_META = {
    "patient_info":   ("Patient Information", "sc-patient"),
    "key_findings":   ("Key Findings",        "sc-findings"),
    "discussion":     ("Discussion",          "sc-discuss"),
    "treatment_plan": ("Treatment Plan",      "sc-plan"),
    "next_steps":     ("Next Steps",          "sc-next"),
}
EMR_FIELDS = [
    ("diagnosis",       "진단명",          False),
    ("stage",           "병기",            False),
    ("chief_complaint", "주호소 / 현병력", False),
    ("imaging",         "영상 소견",        True),
    ("biopsies",        "조직검사 결과",    True),
    ("blood",           "주요 혈액검사",    True),
    ("procedure",       "시술 내역",        False),
    ("surgery",         "수술 내역",        False),
    ("chemotherapy",    "항암 치료",        False),
    ("radiation",       "방사선 치료",      False),
    ("medication",      "현재 투약",        False),
    ("history",         "과거력 / 기타",    True),
]

# ──────────────────────────────────────────────
# API helpers
# ──────────────────────────────────────────────
def api(method, path, **kwargs):
    try:
        r = getattr(requests, method)(f"{API_BASE}{path}", timeout=120, **kwargs)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error("서버에 연결할 수 없습니다. `uvicorn server:app --reload` 를 먼저 실행하세요.")
        st.stop()
    except Exception as e:
        st.error(f"API 오류: {e}")
        return None

# ──────────────────────────────────────────────
# Session state
# ──────────────────────────────────────────────
for k, v in {
    "selected_id":  None,
    "edit_mode":    {},
    "emr_applied":  False,
    "local_emr":    {f: "" for f, *_ in EMR_FIELDS},
    "api_key":      "",
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ──────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        '<div style="font-size:16px;font-weight:700;color:#ffffff;margin-bottom:4px;">'
        'MDT Annotation Dashboard</div>', unsafe_allow_html=True,
    )
    st.markdown('<span class="badge b-generated">Phase 1 · Gemini API</span>',
                unsafe_allow_html=True)
    st.divider()

    nav = st.radio("nav",
        ["📤  File Upload", "🔍  Case Review", "📊  Records & Roadmap"],
        label_visibility="collapsed")
    st.divider()

    # API Key
    st.markdown("**Gemini API Key**")
    api_key_input = st.text_input(
        "key", type="password", placeholder="AIza...",
        value=st.session_state.api_key,
        label_visibility="collapsed",
    )
    if api_key_input != st.session_state.api_key:
        st.session_state.api_key = api_key_input
    if st.session_state.api_key:
        st.success("API key 설정됨")
    else:
        st.caption("API key를 입력하세요")
    st.divider()

    # Pipeline status for selected case
    sel_id = st.session_state.selected_id
    if sel_id:
        data = api("get", f"/cases/{sel_id}") or {}
        c    = data.get("case", {})
        a    = data.get("annotation", {})
        s    = data.get("summary", {})
        steps = [
            ("Transcript loaded",                  bool(c.get("transcript"))),
            ("Consultation segment detected",       bool(c.get("seg_detected"))),
            ("EMR context applied",                 st.session_state.emr_applied or bool(data.get("emr"))),
            ("AI summary generated",               bool(s)),
            ("Clinician review complete",          bool(a.get("approved"))),
        ]
        st.markdown("**Pipeline Status**")
        for name, done in steps:
            ss = "done" if done else "pending"
            st.markdown(
                f'<div class="pipe-step ps-{ss}"><div class="pd pd-{ss}"></div>{name}</div>',
                unsafe_allow_html=True,
            )

    st.divider()
    stats = api("get", "/stats") or {}
    total_a = stats.get("approved", 0)
    st.caption(f"Approved: **{total_a}** / 700")
    if total_a:
        st.progress(min(total_a / 700, 1.0))

# ──────────────────────────────────────────────
# Header
# ──────────────────────────────────────────────
st.markdown(
    '<span class="ha"></span>'
    '<span style="font-size:21px;font-weight:700;color:#ffffff;">MDT Meeting Auto-Summary</span>'
    '&nbsp;<span style="font-size:13px;color:#ffffff;">Annotation Dashboard</span>',
    unsafe_allow_html=True,
)
st.divider()

# ══════════════════════════════════════════════
# FILE UPLOAD TAB
# ══════════════════════════════════════════════
if nav == "📤  File Upload":
    st.markdown(
        '<span class="ha"></span>'
        '<span style="font-weight:600;font-size:15px;">Transcript File Management</span>',
        unsafe_allow_html=True,
    )
    st.caption("STT 전사 파일을 미리 업로드합니다. Case Review 탭에서 검수를 진행하세요.")
    st.markdown("")

    col_up, col_list = st.columns(2, gap="large")

    with col_up:
        st.markdown("**파일 업로드**")
        files = st.file_uploader(
            "STT 전사 파일 (.txt / .vtt / .srt)",
            type=["txt","vtt","srt"],
            accept_multiple_files=True,
            label_visibility="collapsed",
        )
        if files:
            if st.button("업로드 시작", type="primary"):
                results = api("post", "/upload",
                              files=[("files", (f.name, f.read(), "text/plain")) for f in files])
                if results:
                    for r in results:
                        if r["ok"]:
                            st.success(f"✓ {r['filename']}  —  구간 {'탐지됨' if r['seg_detected'] else '미탐지'}")
                        else:
                            st.warning(f"⚠ {r['filename']} — {r.get('reason','')}")
                    st.rerun()

    with col_list:
        st.markdown("**업로드된 파일 목록**")
        cases = api("get", "/cases") or []
        if not cases:
            st.info("업로드된 파일이 없습니다.")
        else:
            for c in cases:
                badge_cls = "b-approved" if c.get("approved") else (
                    "b-generated" if c.get("generated_at") else "b-pending")
                badge_lbl = "Approved" if c.get("approved") else (
                    "Generated" if c.get("generated_at") else "Pending")
                col_a, col_b = st.columns([5,1])
                col_a.markdown(
                    f'📄 `{c["filename"]}`  '
                    f'<span class="badge {badge_cls}">{badge_lbl}</span>',
                    unsafe_allow_html=True,
                )
                if col_b.button("삭제", key=f"del_{c['id']}"):
                    api("delete", f"/cases/{c['id']}")
                    st.rerun()

# ══════════════════════════════════════════════
# CASE REVIEW TAB
# ══════════════════════════════════════════════
elif nav == "🔍  Case Review":
    cases = api("get", "/cases") or []
    if not cases:
        st.warning("업로드된 파일이 없습니다. **File Upload** 탭에서 파일을 먼저 올려주세요.")
        st.stop()

    col_list, col_main = st.columns([1, 3], gap="large")

    # ── Case list ──────────────────────────────
    with col_list:
        st.markdown(
            '<span class="ha"></span>'
            '<span style="font-weight:600;font-size:14px;">Case List</span>'
            f'<span style="font-size:11px;color:#94a3b8;margin-left:8px;">{len(cases)} files</span>',
            unsafe_allow_html=True,
        )
        for c in cases:
            approved   = c.get("approved")
            has_sum    = bool(c.get("generated_at"))
            badge_cls  = "b-approved" if approved else ("b-generated" if has_sum else "b-pending")
            badge_lbl  = "Approved"   if approved else ("Generated"   if has_sum else "Pending")
            is_sel     = st.session_state.selected_id == c["id"]
            row_cls    = "case-row case-row-sel" if is_sel else "case-row"

            st.markdown(
                f'<div class="{row_cls}">'
                f'<div style="font-size:12px;font-weight:600;color:#1e293b;margin-bottom:4px;">{c["filename"]}</div>'
                f'<span class="badge {badge_cls}">{badge_lbl}</span>'
                f'</div>', unsafe_allow_html=True,
            )

            btn_label = "✓ 선택됨" if is_sel else "검수하기"
            btn_type  = "secondary" if is_sel else "primary"
            if st.button(btn_label, key=f"sel_{c['id']}",
                         use_container_width=True, type=btn_type, disabled=is_sel):
                st.session_state.selected_id = c["id"]
                st.session_state.edit_mode   = {}
                st.session_state.emr_applied = False
                # auto-generate if not yet done and api_key set
                if not has_sum and st.session_state.api_key:
                    with st.spinner(f"{c['filename']} — AI 요약 자동 생성 중..."):
                        api("post", "/generate", json={
                            "case_id": c["id"],
                            "api_key": st.session_state.api_key,
                        })
                st.rerun()

    # ── Main review area ────────────────────────
    with col_main:
        sid = st.session_state.selected_id
        if not sid:
            st.info("좌측에서 케이스를 선택하세요. API Key가 설정되어 있으면 선택 즉시 AI 요약이 자동 생성됩니다.")
            st.stop()

        data = api("get", f"/cases/{sid}")
        if not data:
            st.stop()
        c_data = data["case"]
        emr    = data.get("emr", {})
        s_data = data.get("summary", {})
        a_data = data.get("annotation", {})

        inner = st.tabs(["📋  Segment & Summary", "🗂  EMR Context", "✅  Approve & Export"])

        # ── Tab 1: Segment ↔ Summary ────────────
        with inner[0]:
            seg = c_data.get("segment","") or c_data.get("transcript","")
            det = bool(c_data.get("seg_detected"))

            if det:
                st.success("✓ 환자 진료 구간(Clinical Consultation Segment) 자동 탐지")
            else:
                st.warning("⚠ 자동 탐지 실패 — 아래에서 진료 구간을 직접 지정 후 저장하세요.")

            left, right = st.columns([1,1], gap="medium")

            # LEFT: segment (ground truth source)
            with left:
                st.markdown("**환자 진료 구간 — Ground Truth 기준**")
                st.caption("이 구간이 AI 요약의 입력이자 정답 기준입니다.")
                new_seg = st.text_area(
                    "seg_edit", value=seg, height=440,
                    label_visibility="collapsed",
                    disabled=bool(a_data.get("approved")),
                )
                if new_seg != seg and not a_data.get("approved"):
                    if st.button("구간 저장", key="save_seg"):
                        api("patch", "/segment", json={"case_id": sid, "segment": new_seg})
                        st.success("구간 저장됨")
                        st.rerun()

            # RIGHT: AI summary
            with right:
                st.markdown("**AI 생성 요약 — 검수 및 수정**")
                if s_data:
                    st.caption(f"생성: {s_data.get('generated_at','')}  |  {s_data.get('proc_time','-')}s")
                else:
                    st.caption("요약이 아직 없습니다.")

                # re-generate button
                if not a_data.get("approved"):
                    g_col, _ = st.columns([2,3])
                    with g_col:
                        if st.button("🔄 (재)생성", type="primary", use_container_width=True,
                                     disabled=not st.session_state.api_key):
                            if not st.session_state.api_key:
                                st.warning("사이드바에서 API Key를 입력하세요.")
                            else:
                                with st.spinner("Gemini API 요약 생성 중..."):
                                    res = api("post", "/generate", json={
                                        "case_id": sid,
                                        "api_key": st.session_state.api_key,
                                    })
                                if res:
                                    st.success(f"완료 ({res.get('proc_time','-')}s)")
                                    st.rerun()

                if not s_data:
                    st.info("검수하기 버튼 클릭 시 API Key가 있으면 자동 생성됩니다.\n없으면 위 (재)생성 버튼을 누르세요.")
                else:
                    # build editable values dict from s_data (edited_ preferred)
                    ev = {
                        "patient_info":   s_data.get("edited_patient_info")   or s_data.get("patient_info",""),
                        "key_findings":   s_data.get("edited_key_findings")   or s_data.get("key_findings",""),
                        "discussion":     s_data.get("edited_discussion")     or s_data.get("discussion",""),
                        "treatment_plan": s_data.get("edited_treatment_plan") or s_data.get("treatment_plan",""),
                        "next_steps":     s_data.get("edited_next_steps")     or s_data.get("next_steps",""),
                    }
                    edit_mode    = st.session_state.edit_mode
                    is_approved  = bool(a_data.get("approved"))
                    pending_save = {}

                    for sk, (label, card_cls) in SECTION_META.items():
                        content    = ev.get(sk,"")
                        is_editing = edit_mode.get(sk, False)

                        with st.expander(f"**{label}**", expanded=True):
                            if is_approved or not is_editing:
                                st.markdown(
                                    f'<div class="section-card {card_cls}">'
                                    f'<p style="margin:0;font-size:13px;line-height:1.8;color:#1e293b;">{content}</p>'
                                    f'</div>', unsafe_allow_html=True,
                                )
                                if not is_approved:
                                    if st.button("✏ 수정", key=f"eb_{sk}"):
                                        st.session_state.edit_mode[sk] = True
                                        st.rerun()
                            else:
                                new_val = st.text_area(
                                    label, value=content, height=110,
                                    key=f"ea_{sk}", label_visibility="collapsed",
                                )
                                s1, s2, _ = st.columns([1,1,4])
                                if s1.button("저장", key=f"sv_{sk}"):
                                    # update all edited fields
                                    updated = ev.copy()
                                    updated[sk] = new_val
                                    api("patch", "/summary/edit", json={"case_id": sid, **updated})
                                    st.session_state.edit_mode[sk] = False
                                    st.rerun()
                                if s2.button("취소", key=f"cn_{sk}"):
                                    st.session_state.edit_mode[sk] = False
                                    st.rerun()

        # ── Tab 2: EMR ──────────────────────────
        with inner[1]:
            st.markdown(
                '<div class="emr-notice">'
                '🔌 <b>EMR API 연동 예정</b> — 현재 수동 입력 방식입니다.<br>'
                '향후 Raw EMR API 또는 EMR 요약 에이전트 API로 자동 대체됩니다.<br>'
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
                    "**Raw EMR API** — 진단명, 병기, 영상, 조직검사, 혈액검사, 시술, 수술, 항암, 방사선, 투약, 병력\n\n"
                    "**EMR 요약 에이전트 API** — 종합 요약 / 현재 상태 / 경과 기록 / 주요 검사·시술 / 협진 쟁점"
                )
            else:
                # Pre-fill from DB if exists
                local = st.session_state.local_emr
                if emr and not any(local.values()):
                    for key, *_ in EMR_FIELDS:
                        local[key] = emr.get(key, "") or ""
                    st.session_state.local_emr = local

                ca, cb = st.columns(2, gap="medium")
                for i, (key, label, is_long) in enumerate(EMR_FIELDS):
                    col = ca if i % 2 == 0 else cb
                    with col:
                        if is_long:
                            local[key] = st.text_area(
                                label, value=local.get(key,""),
                                height=80, key=f"emr_{key}_{sid}",
                            )
                        else:
                            local[key] = st.text_input(
                                label, value=local.get(key,""),
                                key=f"emri_{key}_{sid}",
                            )
                st.session_state.local_emr = local

                filled = sum(1 for k,*_ in EMR_FIELDS if local.get(k,"").strip())
                st.progress(filled / len(EMR_FIELDS))
                st.caption(f"입력 항목: {filled} / {len(EMR_FIELDS)}")
                st.markdown("")

                # ▶ 반영 버튼
                apply_col, _ = st.columns([2,4])
                with apply_col:
                    if st.button("▶ EMR 반영", type="primary", use_container_width=True,
                                 disabled=filled == 0):
                        res = api("post", "/emr", json={"case_id": sid, **local})
                        if res:
                            st.session_state.emr_applied = True
                            st.success("EMR 컨텍스트가 반영되었습니다. 요약을 다시 생성하면 반영된 EMR이 적용됩니다.")

        # ── Tab 3: Approve & Export ─────────────
        with inner[2]:
            if not s_data:
                st.info("요약이 생성된 후 승인할 수 있습니다.")
                st.stop()

            a_col, e_col = st.columns([1,1], gap="large")

            with a_col:
                st.markdown("**요약 품질 평가**")
                cur_rating = a_data.get("rating", 1) or 1
                rating = st.select_slider(
                    "rating", options=[1,2,3,4,5],
                    value=cur_rating,
                    format_func=lambda x: f"{x} / 5",
                    label_visibility="collapsed",
                )
                st.caption({1:"Poor",2:"Below avg",3:"Acceptable",4:"Good",5:"Excellent"}[rating])

                st.markdown("---")
                if a_data.get("approved"):
                    st.success(f"✅ 승인 완료  \n{a_data.get('approved_at','')}")
                    if st.button("승인 취소"):
                        api("post", "/annotate", json={"case_id": sid, "rating": rating, "approved": False})
                        st.rerun()
                else:
                    if st.button("✅ 승인 & Ground Truth 저장",
                                 type="primary", use_container_width=True):
                        api("post", "/annotate",
                            json={"case_id": sid, "rating": rating, "approved": True})
                        st.success("Ground Truth로 저장되었습니다.")
                        st.rerun()

            with e_col:
                st.markdown("**Export**")
                ev = {
                    "patient_info":   s_data.get("edited_patient_info",""),
                    "key_findings":   s_data.get("edited_key_findings",""),
                    "discussion":     s_data.get("edited_discussion",""),
                    "treatment_plan": s_data.get("edited_treatment_plan",""),
                    "next_steps":     s_data.get("edited_next_steps",""),
                }
                fname = c_data.get("filename","case")
                ts    = datetime.now().strftime("%Y%m%d_%H%M")

                js = json.dumps(ev, ensure_ascii=False, indent=2)
                st.download_button("JSON 다운로드", data=js,
                    file_name=f"mdt_{fname}_{ts}.json",
                    mime="application/json", use_container_width=True)

                txt = "\n\n".join(
                    f"[{SECTION_META[k][0].upper()}]\n{v}" for k,v in ev.items()
                )
                st.download_button("TXT 다운로드", data=txt,
                    file_name=f"mdt_{fname}_{ts}.txt",
                    mime="text/plain", use_container_width=True)

# ══════════════════════════════════════════════
# RECORDS & ROADMAP TAB
# ══════════════════════════════════════════════
elif nav == "📊  Records & Roadmap":
    stats = api("get", "/stats") or {}
    total_a = stats.get("approved", 0)
    pct     = min(total_a / 700 * 100, 100)

    c1,c2,c3,c4 = st.columns(4)
    for col, val, lbl in [
        (c1, str(stats.get("total",0)),    "Total cases"),
        (c2, str(total_a),                  "Approved"),
        (c3, f"{stats.get('avg_rating',0)}/5", "Avg. quality"),
        (c4, f"{stats.get('avg_proc_time',0)}s","Avg. proc. time"),
    ]:
        col.markdown(
            f'<div class="kpi-box"><div class="kpi-value">{val}</div>'
            f'<div class="kpi-label">{lbl}</div></div>', unsafe_allow_html=True,
        )
    st.progress(pct / 100)
    st.caption(f"Fine-tuning threshold: 700 approved  ({total_a} / 700)")
    st.divider()

    # Roadmap
    st.markdown(
        '<span class="ha"></span>'
        '<span style="font-weight:600;font-size:15px;">Development Roadmap</span>',
        unsafe_allow_html=True,
    )
    phases = [
        ("Phase 0","Mar 2026",     "done",   "Prototype Validation", ["Gemini API POC 완료","파이프라인 설계","EMR 보정 확인"]),
        ("Phase 1","Apr-Jun 2026","active",  "Data & Infrastructure",["IRB 승인","Annotation Dashboard","EMR API 설계"]),
        ("Phase 2","Jul-Sep 2026","pending", "Model Development",    ["온-프레미스 GPU","LLM Fine-tuning","품질 고도화"]),
        ("Phase 3","Oct-Dec 2026","pending", "Clinical Validation",  ["300건+ 실증","KPI 달성","EMR API 완전 연동"]),
    ]
    cm={"done":"#f0fdf4","active":"#eff6ff","pending":"#f8fafc"}
    bm={"done":"#bbf7d0","active":"#bfdbfe","pending":"#e2e8f0"}
    tm={"done":"#166534","active":"#1d4ed8","pending":"#94a3b8"}
    lm={"done":"Complete","active":"In progress","pending":"Planned"}
    cols=st.columns(4)
    for col,(phase,period,status,title,items) in zip(cols,phases):
        ih="".join(f'<li style="font-size:12px;color:#334155;margin-bottom:3px;">{i}</li>' for i in items)
        col.markdown(
            f'<div style="background:{cm[status]};border:1px solid {bm[status]};'
            f'border-radius:8px;padding:16px;min-height:170px;">'
            f'<div style="font-size:11px;font-weight:700;color:{tm[status]};margin-bottom:2px;">{phase}·{period}</div>'
            f'<div style="font-weight:600;font-size:13px;color:#0f172a;margin-bottom:5px;">{title}</div>'
            f'<span style="font-size:10px;font-weight:600;background:{cm[status]};color:{tm[status]};'
            f'padding:2px 8px;border-radius:4px;border:1px solid {bm[status]};">{lm[status]}</span>'
            f'<ul style="padding-left:14px;margin:9px 0 0;">{ih}</ul></div>',
            unsafe_allow_html=True,
        )
    st.divider()

    # Approved records table
    st.markdown(
        '<span class="ha"></span>'
        '<span style="font-weight:600;font-size:15px;">Approved Ground Truth Records</span>',
        unsafe_allow_html=True,
    )
    records = api("get", "/records") or []
    if not records:
        st.info("승인된 케이스가 없습니다.")
    else:
        import pandas as pd
        df = pd.DataFrame([{
            "ID":        r["id"],
            "File":      r["filename"],
            "Rating":    f"{r.get('rating','-')}/5",
            "Proc.(s)":  r.get("proc_time","-"),
            "Approved":  r.get("approved_at","-"),
        } for r in records])
        st.dataframe(df, use_container_width=True, hide_index=True)

        all_json = json.dumps(records, ensure_ascii=False, indent=2)
        st.download_button(
            "전체 Ground Truth 다운로드 (JSON)", data=all_json,
            file_name=f"ground_truth_{datetime.now().strftime('%Y%m%d')}.json",
            mime="application/json",
        )
