# MDT Meeting Auto-Summary — Annotation Dashboard

A clinical annotation tool for reviewing and validating AI-generated structured summaries of Multidisciplinary Team (MDT) meeting transcripts. Built for oncology teams at Bundang CHA Hospital, focusing on biliary tract and pancreatic cancer MDT meetings.

---

## Overview

This dashboard supports a **human-in-the-loop annotation workflow** where:

1. STT transcript files are uploaded in advance by an administrator
2. Clinicians select a case, review the auto-detected **patient consultation segment** (환자 진료 구간), and optionally inject EMR context
3. A **Gemini API**-powered LLM generates a structured 5-section clinical summary
4. Clinicians edit, rate, and approve the summary
5. Approved summaries are stored as **ground truth** records for future LLM fine-tuning

The system is designed as a **Label Studio-style annotation tool** — the patient consultation segment serves as the ground truth reference, and the AI output is reviewed against it.

---

## Project Structure

```
.
├── app.py                  # Streamlit frontend (clinician-facing dashboard)
├── server.py               # FastAPI backend (REST API + SQLite DB + LLM)
├── requirements.txt        # Python dependencies
├── mdt_annotation.db       # SQLite database (auto-created on first run)
└── uploads/                # Uploaded transcript files (auto-created)
```

---

## Architecture

```
┌─────────────────────┐        REST API        ┌──────────────────────────┐
│   Streamlit (app.py) │  ◄──────────────────►  │  FastAPI (server.py)     │
│   Clinician UI       │    localhost:8000       │                          │
│   localhost:8501     │                         │  ┌────────────────────┐  │
└─────────────────────┘                         │  │  SQLite DB         │  │
                                                 │  │  · cases           │  │
                                                 │  │  · emr_context     │  │
                                                 │  │  · summaries       │  │
                                                 │  │  · annotations     │  │
                                                 │  └────────────────────┘  │
                                                 │                          │
                                                 │  ┌────────────────────┐  │
                                                 │  │  Gemini API        │  │
                                                 │  │  gemini-2.5-flash  │  │
                                                 │  └────────────────────┘  │
                                                 └──────────────────────────┘
```

---

## Database Schema

```sql
cases          -- transcript files, segment detection results, status
emr_context    -- EMR fields per case (versioned; latest used for generation)
summaries      -- AI-generated output + clinician-edited versions
annotations    -- quality rating + approval status + timestamp
```

**Case status lifecycle:** `pending` → `generated` → `approved`

---

## Getting Started

### Prerequisites

- Python 3.10+
- A valid [Google Gemini API key](https://aistudio.google.com/apikey)

### Installation

```bash
git clone <repo-url>
cd mdt-annotation-dashboard
pip install -r requirements.txt
```

### Running

Open **two terminals**:

```bash
# Terminal 1 — Backend
uvicorn server:app --reload --port 8000

# Terminal 2 — Frontend
streamlit run app.py
```

Then open [http://localhost:8501](http://localhost:8501) in your browser.

The API docs are available at [http://localhost:8000/docs](http://localhost:8000/docs).

---

## Usage

### Tab 1 — File Upload *(administrator)*

- Upload one or more STT transcript files (`.txt`, `.vtt`, `.srt`)
- On upload, the backend automatically attempts to detect the **patient consultation segment** using greeting pattern heuristics (e.g., `안녕하세요`)
- Files can be deleted individually

### Tab 2 — Case Review *(clinician)*

**Case List (left panel)**
- All uploaded cases are listed with status badges: `Pending` / `Generated` / `Approved`
- Clicking **검수하기** selects the case and automatically triggers AI summary generation if an API key is set and no summary exists yet

**Segment & Summary (inner tab)**
- **Left**: Patient consultation segment — the ground truth reference. Editable and saveable if auto-detection was incorrect
- **Right**: AI-generated structured summary across 5 sections. Each section can be individually edited and saved. Re-generation is available at any time

**EMR Context (inner tab)**
- Manually enter any available EMR fields (partial input is accepted)
- Click **▶ EMR 반영** to persist the context to the database
- Re-generating the summary after applying EMR context will incorporate the new information
- Designed to be replaced by a live EMR API integration in a future phase

> **EMR API integration (planned):**
> Two modes are stubbed out in `server.py`:
> - **Mode A — Raw EMR API**: fetches structured fields directly (diagnosis, imaging, biopsies, blood, medication, etc.)
> - **Mode B — EMR Summary Agent API**: fetches pre-summarised output (comprehensive summary, current status, progress record, key procedures, consultation issues)
> To activate, replace the body of `get_emr_context()` in the backend with the appropriate `fetch_emr_from_api()` call.

**Approve & Export (inner tab)**
- Rate summary quality (1–5 scale)
- Click **✅ 승인 & Ground Truth 저장** to write the final edited summary to the `annotations` table
- Export the approved summary as JSON or TXT

### Tab 3 — Records & Roadmap

- KPI dashboard: total cases, approved count, average quality rating, average processing time
- Progress bar toward the 700-record fine-tuning threshold
- Development roadmap (Phase 0–3)
- Full table of approved ground truth records with download

---

## Summary Output Structure

Each AI-generated summary contains five sections:

| Section | Description |
|---|---|
| **Patient Information** | Patient background and diagnosis summary (2–3 sentences) |
| **Key Findings** | Imaging and lab findings, notable value changes (3–5 sentences) |
| **Discussion** | Specialty-by-specialty opinions and treatment options discussed (4–6 sentences) |
| **Treatment Plan** | Confirmed treatment direction and plan (2–4 sentences) |
| **Next Steps** | Follow-up tests, referrals, and scheduling (2–3 sentences) |

---

## EMR Context Fields

The following fields are accepted as EMR input (all optional):

| Field | Description |
|---|---|
| `diagnosis` | Primary diagnosis |
| `stage` | Disease stage (e.g., T2N0M0) |
| `chief_complaint` | Chief complaint / history of present illness |
| `imaging` | Summary of imaging findings |
| `biopsies` | Pathology / biopsy results |
| `blood` | Key lab values (e.g., CA19-9, CEA, bilirubin) |
| `procedure` | Recent procedures (e.g., ERCP, stenting) |
| `surgery` | Surgical history |
| `chemotherapy` | Chemotherapy history |
| `radiation` | Radiation therapy history |
| `medication` | Current medications |
| `history` | Past medical history / other |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/cases` | List all cases with status |
| `POST` | `/upload` | Upload transcript files |
| `GET` | `/cases/{id}` | Get full case detail (transcript, EMR, summary, annotation) |
| `DELETE` | `/cases/{id}` | Delete case and all related records |
| `POST` | `/emr` | Save EMR context for a case |
| `PATCH` | `/segment` | Update patient consultation segment |
| `POST` | `/generate` | Generate AI summary (requires `api_key`) |
| `PATCH` | `/summary/edit` | Save clinician edits to a summary |
| `POST` | `/annotate` | Save rating and approval status |
| `GET` | `/records` | List all approved ground truth records |
| `GET` | `/stats` | Aggregate statistics |

---

## Development Roadmap

| Phase | Period | Status | Focus |
|---|---|---|---|
| Phase 0 | Mar 2026 | ✅ Complete | Gemini API prototype validation, pipeline design |
| Phase 1 | Apr–Jun 2026 | 🔵 In progress | IRB approval, annotation dashboard, EMR API design |
| Phase 2 | Jul–Sep 2026 | ⬜ Planned | On-premises GPU setup, LLM fine-tuning |
| Phase 3 | Oct–Dec 2026 | ⬜ Planned | 300+ case clinical validation, full EMR API integration |

Fine-tuning will be initiated once **700 approved ground truth records** are accumulated.

---

## Notes

- Patient audio files and transcripts contain sensitive medical data. All processing occurs on-premises; no patient data is sent externally except for the text passed to the Gemini API.
- The Gemini API call includes only the patient consultation segment text and the EMR context fields — never raw audio.
- When transitioning to on-premises LLM inference, the `run_llm()` function in `server.py` should be replaced with a local model call (e.g., vLLM endpoint), with no changes required to the frontend.
- The SQLite database is suitable for Phase 1 annotation volumes. Migration to PostgreSQL is recommended before production deployment.
