# mdt-summary-agent

> AI-powered multidisciplinary team (MDT) meeting auto-summarization using Gemini 2.5 Flash + EMR context injection.

Converts STT-transcribed meeting text into structured clinical summaries — reviewed and approved by clinicians to accumulate Ground Truth for future fine-tuning.

---

## Features

- **Structured output** — Patient info / Key findings / Discussion / Treatment plan / Next steps
- **EMR context injection** — Corrects medical term misrecognition (diagnosis, medications, lab values) without a custom glossary
- **Patient segment detection** — Identifies clinician-patient interaction segments via text pattern matching
- **Clinician review dashboard** — Section-level editing, 5-star quality rating, approval workflow
- **Ground Truth export** — JSON export of approved summaries for Phase 2 LLM fine-tuning

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run
streamlit run app.py
```

Open http://localhost:8501 in your browser.

Add your Gemini API key in the sidebar. Get one at [aistudio.google.com/apikey](https://aistudio.google.com/apikey).

---

## Usage

1. **Input & EMR tab** — Paste STT transcript or upload `.txt` / `.vtt` / `.srt`. Fill in EMR fields (diagnosis, medications, lab results, previous summary).
2. **Click "AI 구조화 요약 생성"** — Gemini 2.5 Flash generates a structured summary with EMR context.
3. **Summary Review tab** — Verify each section, edit if needed, rate quality (1–5), then approve.
4. **History tab** — Track accumulated Ground Truth records and download as JSON.

---

## Deployment (Free)

**Streamlit Community Cloud**

1. Push this repo to GitHub
2. Connect at [share.streamlit.io](https://share.streamlit.io)
3. Add your API key under **Settings → Secrets**:
   ```toml
   GEMINI_API_KEY = "AIza..."
   ```

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM | Gemini 2.5 Flash (Phase 1) → LLaMA-3.1 8B fine-tuned (Phase 2) |
| STT | OpenAI Whisper Large (auxiliary) |
| Audio preprocessing | FFmpeg + Silero VAD |
| Backend | FastAPI (Python) |
| Frontend | Streamlit |
| Experiment tracking | MLflow |
| Database | PostgreSQL |

---

## Roadmap

| Phase | Period | Goal |
|---|---|---|
| Phase 0 ✅ | 2026.03 | Gemini prototype validation, pipeline design |
| Phase 1 🔄 | 2026.04–06 | IRB approval, data collection, review UI |
| Phase 2 ⏳ | 2026.07–09 | On-premises GPU, LLM fine-tuning |
| Phase 3 ⏳ | 2026.10–12 | 300+ case validation, full EMR integration |

Fine-tuning threshold: **700 approved Ground Truth records**

---

## KPI Targets

- 85% reduction in meeting documentation time
- F1-score ≥ 0.80 for structured summary completeness
- Clinician satisfaction ≥ 80% (4.0/5.0)
- 300+ real-world validation cases
