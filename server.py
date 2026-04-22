"""
MDT Annotation Dashboard — FastAPI Backend
Handles: file storage, DB (SQLite), LLM summary generation
Run: uvicorn server:app --reload --port 8000
"""

import os, json, re, time, sqlite3, shutil
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import google.generativeai as genai

# ──────────────────────────────────────────────
# Paths & DB
# ──────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
DB_PATH    = BASE_DIR / "mdt_annotation.db"
UPLOAD_DIR.mkdir(exist_ok=True)

# ──────────────────────────────────────────────
# DB helpers
# ──────────────────────────────────────────────
@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS cases (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            filename    TEXT UNIQUE NOT NULL,
            transcript  TEXT NOT NULL,
            segment     TEXT,
            seg_detected INTEGER DEFAULT 0,
            status      TEXT DEFAULT 'pending',
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS emr_context (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id        INTEGER NOT NULL,
            diagnosis      TEXT, stage         TEXT, chief_complaint TEXT,
            imaging        TEXT, biopsies      TEXT, blood           TEXT,
            procedure      TEXT, surgery       TEXT, chemotherapy    TEXT,
            radiation      TEXT, medication    TEXT, history         TEXT,
            applied_at     TEXT,
            FOREIGN KEY (case_id) REFERENCES cases(id)
        );

        CREATE TABLE IF NOT EXISTS summaries (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id        INTEGER NOT NULL UNIQUE,
            patient_info   TEXT, key_findings  TEXT, discussion     TEXT,
            treatment_plan TEXT, next_steps    TEXT,
            edited_patient_info   TEXT, edited_key_findings  TEXT,
            edited_discussion     TEXT, edited_treatment_plan TEXT,
            edited_next_steps     TEXT,
            proc_time      REAL,
            generated_at   TEXT,
            FOREIGN KEY (case_id) REFERENCES cases(id)
        );

        CREATE TABLE IF NOT EXISTS annotations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id     INTEGER NOT NULL UNIQUE,
            rating      INTEGER DEFAULT 0,
            approved    INTEGER DEFAULT 0,
            approved_at TEXT,
            FOREIGN KEY (case_id) REFERENCES cases(id)
        );
        """)

init_db()

# ──────────────────────────────────────────────
# FastAPI app
# ──────────────────────────────────────────────
app = FastAPI(title="MDT Annotation API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# ──────────────────────────────────────────────
# LLM helpers
# ──────────────────────────────────────────────
EMR_LABELS = [
    ("diagnosis","진단명"), ("stage","병기"), ("chief_complaint","주호소/현병력"),
    ("imaging","영상소견"), ("biopsies","조직검사"), ("blood","혈액검사"),
    ("procedure","시술"), ("surgery","수술"), ("chemotherapy","항암"),
    ("radiation","방사선"), ("medication","투약"), ("history","과거력"),
]
SECTION_KEYS = ["patient_info","key_findings","discussion","treatment_plan","next_steps"]

GREETING_PATTERNS = ["안녕하세요","안녕하십니까","반갑습니다","오셨군요","환자분"]

def detect_segment(transcript: str):
    lines = transcript.splitlines()
    for i, line in enumerate(lines):
        if any(p in line for p in GREETING_PATTERNS):
            return True, "\n".join(lines[i:]).strip()
    return False, ""

def safe_parse(raw: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?","",raw.strip(),flags=re.MULTILINE)
    cleaned = re.sub(r"```$","",cleaned.strip(),flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if m:
        cand = re.sub(r",\s*([}\]])", r"\1", m.group(0))
        try:
            return json.loads(cand)
        except Exception:
            for end in range(len(cand)-1, 0, -1):
                if cand[end] == "}":
                    try: return json.loads(cand[:end+1])
                    except Exception: continue
    result = {}
    for key in SECTION_KEYS:
        m2 = re.search(rf'"{key}"\s*:\s*"((?:[^"\\]|\\.)*)"', cleaned, re.DOTALL)
        if m2:
            result[key] = m2.group(1).replace('\\"','"').replace("\\n","\n")
    if result:
        return result
    raise ValueError(f"파싱 실패: {raw[:400]}")

def build_prompt(segment: str, emr: dict) -> str:
    emr_block = "\n".join(
        f"{label}: {emr.get(key,'') or '-'}"
        for key, label in EMR_LABELS
        if emr.get(key,"").strip()
    ) or "(EMR 정보 없음)"
    return (
        "You are a clinical AI for Korean MDT meetings. "
        "Output ONLY raw JSON, no markdown, no fences, no extra text.\n\n"
        f"[EMR Context]\n{emr_block}\n\n"
        f"[환자 진료 구간]\n{segment[:8000]}\n\n"
        'Return: {"patient_info":"2~3문장","key_findings":"3~5문장",'
        '"discussion":"4~6문장","treatment_plan":"2~4문장","next_steps":"2~3문장"}'
    )

def run_llm(segment: str, emr: dict, api_key: str) -> tuple:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")
    t0    = time.time()
    resp  = model.generate_content(
        build_prompt(segment, emr),
        generation_config=genai.GenerationConfig(temperature=0.1, max_output_tokens=2048),
    )
    result  = safe_parse(resp.text)
    elapsed = round(time.time() - t0, 1)
    for k in SECTION_KEYS:
        if k not in result or not str(result.get(k,"")).strip():
            result[k] = "-"
    return result, elapsed

# ──────────────────────────────────────────────
# Pydantic models
# ──────────────────────────────────────────────
class EMRPayload(BaseModel):
    case_id: int
    diagnosis: str = ""; stage: str = ""; chief_complaint: str = ""
    imaging: str = ""; biopsies: str = ""; blood: str = ""
    procedure: str = ""; surgery: str = ""; chemotherapy: str = ""
    radiation: str = ""; medication: str = ""; history: str = ""

class SummaryEditPayload(BaseModel):
    case_id: int
    patient_info: str = ""; key_findings: str = ""; discussion: str = ""
    treatment_plan: str = ""; next_steps: str = ""

class AnnotationPayload(BaseModel):
    case_id: int
    rating: int
    approved: bool = False

class GeneratePayload(BaseModel):
    case_id: int
    api_key: str

class SegmentPayload(BaseModel):
    case_id: int
    segment: str

# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────

@app.get("/cases")
def list_cases():
    with get_db() as db:
        rows = db.execute("""
            SELECT c.id, c.filename, c.seg_detected, c.status, c.created_at,
                   a.approved, a.rating,
                   s.generated_at
            FROM cases c
            LEFT JOIN annotations a ON a.case_id = c.id
            LEFT JOIN summaries   s ON s.case_id = c.id
            ORDER BY c.created_at DESC
        """).fetchall()
    return [dict(r) for r in rows]


@app.post("/upload")
async def upload_files(files: list[UploadFile] = File(...)):
    results = []
    with get_db() as db:
        for f in files:
            content = (await f.read()).decode("utf-8", errors="ignore")
            dest    = UPLOAD_DIR / f.filename
            dest.write_text(content, encoding="utf-8")
            detected, segment = detect_segment(content)
            try:
                db.execute(
                    "INSERT INTO cases (filename, transcript, segment, seg_detected, status, created_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (f.filename, content, segment, int(detected), "pending",
                     datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                )
                results.append({"filename": f.filename, "ok": True, "seg_detected": detected})
            except sqlite3.IntegrityError:
                results.append({"filename": f.filename, "ok": False, "reason": "already exists"})
    return results


@app.delete("/cases/{case_id}")
def delete_case(case_id: int):
    with get_db() as db:
        row = db.execute("SELECT filename FROM cases WHERE id=?", (case_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Not found")
        (UPLOAD_DIR / row["filename"]).unlink(missing_ok=True)
        db.execute("DELETE FROM emr_context  WHERE case_id=?", (case_id,))
        db.execute("DELETE FROM summaries    WHERE case_id=?", (case_id,))
        db.execute("DELETE FROM annotations  WHERE case_id=?", (case_id,))
        db.execute("DELETE FROM cases        WHERE id=?",      (case_id,))
    return {"ok": True}


@app.get("/cases/{case_id}")
def get_case(case_id: int):
    with get_db() as db:
        c = db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
        if not c:
            raise HTTPException(404)
        emr = db.execute(
            "SELECT * FROM emr_context WHERE case_id=? ORDER BY id DESC LIMIT 1", (case_id,)
        ).fetchone()
        s = db.execute("SELECT * FROM summaries   WHERE case_id=?", (case_id,)).fetchone()
        a = db.execute("SELECT * FROM annotations WHERE case_id=?", (case_id,)).fetchone()
    return {
        "case":       dict(c),
        "emr":        dict(emr) if emr else {},
        "summary":    dict(s)   if s   else {},
        "annotation": dict(a)   if a   else {},
    }


@app.post("/emr")
def save_emr(payload: EMRPayload):
    with get_db() as db:
        db.execute(
            "INSERT INTO emr_context "
            "(case_id,diagnosis,stage,chief_complaint,imaging,biopsies,blood,"
            "procedure,surgery,chemotherapy,radiation,medication,history,applied_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (payload.case_id, payload.diagnosis, payload.stage, payload.chief_complaint,
             payload.imaging, payload.biopsies, payload.blood, payload.procedure,
             payload.surgery, payload.chemotherapy, payload.radiation,
             payload.medication, payload.history,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
    return {"ok": True}


@app.patch("/segment")
def update_segment(payload: SegmentPayload):
    with get_db() as db:
        db.execute(
            "UPDATE cases SET segment=?, seg_detected=1 WHERE id=?",
            (payload.segment, payload.case_id)
        )
    return {"ok": True}


@app.post("/generate")
def generate_summary(payload: GeneratePayload):
    with get_db() as db:
        c   = db.execute("SELECT * FROM cases WHERE id=?", (payload.case_id,)).fetchone()
        emr = db.execute(
            "SELECT * FROM emr_context WHERE case_id=? ORDER BY id DESC LIMIT 1",
            (payload.case_id,)
        ).fetchone()
    if not c:
        raise HTTPException(404)
    segment = c["segment"] or c["transcript"]
    if not segment.strip():
        raise HTTPException(400, "Segment is empty")

    emr_dict = dict(emr) if emr else {}
    try:
        result, elapsed = run_llm(segment, emr_dict, payload.api_key)
    except Exception as e:
        raise HTTPException(500, str(e))

    with get_db() as db:
        existing = db.execute("SELECT id FROM summaries WHERE case_id=?", (payload.case_id,)).fetchone()
        if existing:
            db.execute(
                "UPDATE summaries SET patient_info=?,key_findings=?,discussion=?,"
                "treatment_plan=?,next_steps=?,edited_patient_info=?,edited_key_findings=?,"
                "edited_discussion=?,edited_treatment_plan=?,edited_next_steps=?,"
                "proc_time=?,generated_at=? WHERE case_id=?",
                (result["patient_info"], result["key_findings"], result["discussion"],
                 result["treatment_plan"], result["next_steps"],
                 result["patient_info"], result["key_findings"], result["discussion"],
                 result["treatment_plan"], result["next_steps"],
                 elapsed, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 payload.case_id)
            )
        else:
            db.execute(
                "INSERT INTO summaries "
                "(case_id,patient_info,key_findings,discussion,treatment_plan,next_steps,"
                "edited_patient_info,edited_key_findings,edited_discussion,"
                "edited_treatment_plan,edited_next_steps,proc_time,generated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (payload.case_id,
                 result["patient_info"], result["key_findings"], result["discussion"],
                 result["treatment_plan"], result["next_steps"],
                 result["patient_info"], result["key_findings"], result["discussion"],
                 result["treatment_plan"], result["next_steps"],
                 elapsed, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
        db.execute(
            "UPDATE cases SET status='generated' WHERE id=?", (payload.case_id,)
        )
    return {"ok": True, "result": result, "proc_time": elapsed}


@app.patch("/summary/edit")
def edit_summary(payload: SummaryEditPayload):
    with get_db() as db:
        db.execute(
            "UPDATE summaries SET edited_patient_info=?,edited_key_findings=?,"
            "edited_discussion=?,edited_treatment_plan=?,edited_next_steps=? "
            "WHERE case_id=?",
            (payload.patient_info, payload.key_findings, payload.discussion,
             payload.treatment_plan, payload.next_steps, payload.case_id)
        )
    return {"ok": True}


@app.post("/annotate")
def annotate(payload: AnnotationPayload):
    with get_db() as db:
        existing = db.execute(
            "SELECT id FROM annotations WHERE case_id=?", (payload.case_id,)
        ).fetchone()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if payload.approved else None
        if existing:
            db.execute(
                "UPDATE annotations SET rating=?,approved=?,approved_at=? WHERE case_id=?",
                (payload.rating, int(payload.approved), now, payload.case_id)
            )
        else:
            db.execute(
                "INSERT INTO annotations (case_id,rating,approved,approved_at) VALUES (?,?,?,?)",
                (payload.case_id, payload.rating, int(payload.approved), now)
            )
        if payload.approved:
            db.execute("UPDATE cases SET status='approved' WHERE id=?", (payload.case_id,))
    return {"ok": True}


@app.get("/records")
def get_records():
    with get_db() as db:
        rows = db.execute("""
            SELECT c.id, c.filename, c.status, c.created_at,
                   a.rating, a.approved, a.approved_at,
                   s.proc_time, s.generated_at,
                   s.edited_patient_info, s.edited_key_findings,
                   s.edited_discussion, s.edited_treatment_plan,
                   s.edited_next_steps
            FROM cases c
            LEFT JOIN annotations a ON a.case_id = c.id
            LEFT JOIN summaries   s ON s.case_id = c.id
            WHERE a.approved = 1
            ORDER BY a.approved_at DESC
        """).fetchall()
    return [dict(r) for r in rows]


@app.get("/stats")
def get_stats():
    with get_db() as db:
        total     = db.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
        approved  = db.execute("SELECT COUNT(*) FROM annotations WHERE approved=1").fetchone()[0]
        generated = db.execute("SELECT COUNT(*) FROM summaries").fetchone()[0]
        avg_r_row = db.execute(
            "SELECT AVG(rating) FROM annotations WHERE approved=1"
        ).fetchone()[0]
        avg_r     = round(avg_r_row, 1) if avg_r_row else 0
        avg_t_row = db.execute("SELECT AVG(proc_time) FROM summaries").fetchone()[0]
        avg_t     = round(avg_t_row, 1) if avg_t_row else 0
    return {
        "total": total, "approved": approved, "generated": generated,
        "avg_rating": avg_r, "avg_proc_time": avg_t,
    }
