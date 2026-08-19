# MedAI — Clinical AI Dashboard for Doctors

A full-stack Django web application that assists doctors with patient management, clinical document generation, AI-powered medical chat, and Retrieval-Augmented Generation (RAG) over uploaded medical documents.

---

## What It Does

MedAI gives doctors a single dashboard to:

- **Manage patients** — create, edit, and track patient records with MRN, demographics, and visit history
- **Start clinical visits** — open a visit workspace with an AI chat assistant that answers questions grounded in the patient's uploaded documents (RAG)
- **Generate clinical documents** — deterministic PDF generation for consultation summaries, prescriptions, medical certificates, and referral letters
- **Upload & analyze medical documents** — PDFs are extracted, chunked, de-identified (PHI/PII removal), embedded, and stored in a vector database for semantic search
- **Generate AI reports** — structured patient data is sent to an LLM which produces a formatted report rendered as a downloadable PDF
- **Track tasks & follow-ups** — dashboard with due-today tasks, upcoming appointments, and per-patient task management

---

## Use Cases

| Scenario | How MedAI Helps |
|----------|----------------|
| Doctor uploads a lab report PDF | Text is extracted, chunked, de-identified, and embedded — becomes searchable by the AI chat during visits |
| Doctor starts a visit and asks "What were the patient's last cholesterol levels?" | RAG pipeline retrieves relevant chunks from uploaded documents, reranks them, and the LLM answers with citations |
| Doctor needs to write a referral letter | Fills out a form → deterministic PDF is generated with patient info, diagnosis, and doctor's signature block |
| Doctor needs a medical certificate | Selects dates and diagnosis → PDF is generated instantly |
| Doctor wants a patient summary report | Clicks "Generate Report" → LLM produces a structured JSON report → rendered as HTML → downloadable PDF |

---

## Tech Stack

### Backend
- **Django 6.0** — web framework
- **PostgreSQL** + **pgvector** — relational database with vector similarity search
- **fpdf2** — deterministic clinical document PDF generation (no native deps)

### AI / ML Pipeline
- **OpenRouter API** (OpenAI-compatible) — LLM inference (`nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free`)
- **sentence-transformers** — local embeddings (`all-MiniLM-L6-v2`, 384 dimensions) + cross-encoder reranking (`ms-marco-MiniLM-L6-v2`)
- **Microsoft Presidio** — PHI/PII detection and anonymization
- **LangChain text splitters** — section-aware recursive chunking
- **pypdf** — PDF text extraction

### Frontend
- **Tailwind CSS 3.4** — utility-first CSS via Node.js build
- **Vanilla JavaScript** — sidebar toggle, async chat, medication form builder
- **SVG icon system** — inline Heroicons (outline) via Django template include

---

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+ (for Tailwind CSS build)
- PostgreSQL 14+ with pgvector extension

### 1. Clone & install dependencies

```bash
git clone <repo-url> medai
cd medai

# Python dependencies
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt

# Frontend build
npm install
npx tailwindcss -i static/src/input.css -o static/css/tailwind.css --minify
```

### 2. Set up PostgreSQL

```sql
CREATE DATABASE medai_rag;
CREATE EXTENSION IF NOT EXISTS vector;
```

### 3. Configure environment variables

Create a `.env` file in the project root:

```env
# Django
SECRET_KEY=your-django-secret-key-here
DEBUG=True

# Database
DB_NAME=medai_rag
DB_USER=postgres
DB_PASSWORD=your-db-password
DB_HOST=localhost
DB_PORT=5432

# LLM API (OpenRouter — https://openrouter.ai/keys)
OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

### 4. Run migrations & start

```bash
python manage.py migrate
python manage.py createsuperuser   # optional, for admin access
python manage.py runserver
```

Visit [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SECRET_KEY` | **Yes** | — | Django secret key for cryptographic signing. Generate with `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `DEBUG` | No | `True` | Set to `False` in production |
| `DB_NAME` | No | `medai_rag` | PostgreSQL database name |
| `DB_USER` | No | `postgres` | PostgreSQL username |
| `DB_PASSWORD` | No | `''` | PostgreSQL password |
| `DB_HOST` | No | `localhost` | PostgreSQL host |
| `DB_PORT` | No | `5432` | PostgreSQL port |
| `OPENROUTER_API_KEY` | **Yes** | — | API key from [OpenRouter](https://openrouter.ai/keys). Used for LLM chat, report generation, and document analysis |

### LLM Model Configuration (in `settings.py`)

| Setting | Default | Description |
|---------|---------|-------------|
| `LLM_MODEL` | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | OpenRouter model ID |
| `RAG_EMBEDDINGS_ENABLED` | `True` | Enable local embeddings + pgvector |
| `EMBEDDING_DIMENSIONS` | `384` | Must match the embedding model |
| `RAG_CANDIDATE_K` | `20` | Candidates before reranking |
| `RAG_FINAL_K` | `5` | Final results after reranking |

---

## Project Structure

```
medai/
├── manage.py
├── requirements.txt
├── package.json                        # Tailwind CSS
├── .env                                # Environment variables (gitignored)
│
├── myproject/                          # Django project config
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
│
├── apps/
│   ├── accounts/                       # Doctor auth & registration
│   │   ├── models.py                   # Doctor profile
│   │   └── views.py                    # Register, login, profile, password reset
│   │
│   ├── patients/                       # Patient records
│   │   ├── models.py                   # Patient (MRN, DOB, sex, demographics)
│   │   └── templatetags/
│   │       └── patient_extras.py       # Age calculation filter
│   │
│   ├── tasks/                          # Dashboard tasks & follow-ups
│   │   ├── models.py                   # Task (title, due_at, status)
│   │   └── views.py                    # Dashboard, CRUD
│   │
│   ├── visits/                         # Clinical encounters + AI chat
│   │   ├── models.py                   # Visit + VisitMessage
│   │   └── views.py                    # Visit workspace, async message send
│   │
│   ├── documents/                      # Document pipeline + clinical PDFs
│   │   ├── models.py                   # Document, DocumentChunk, DocumentAnalysis,
│   │   │                               #   GeneratedClinicalDocument
│   │   ├── clinical_docs.py            # fpdf2 PDF builders (4 document types)
│   │   ├── clinical_forms.py           # Django forms for clinical docs
│   │   ├── pdf.py                      # WeasyPrint wrapper (report PDFs)
│   │   └── services.py                 # Upload processing pipeline
│   │
│   └── ai/                             # AI/RAG pipeline
│       ├── facade.py                   # AIOrchestrator — single entry point
│       ├── llm.py                      # OpenRouter API client
│       ├── prompts.py                  # Prompt templates
│       ├── chunking.py                 # Section-aware PDF chunking
│       ├── deidentify.py              # PHI/PII detection & anonymization
│       ├── embeddings.py              # Local sentence-transformers
│       ├── retrieval.py               # RAG retrieval + reranking
│       ├── vectorstore.py             # pgvector similarity search
│       └── report_generation.py       # Patient report pipeline
│
├── templates/                          # Django HTML templates
│   ├── base.html                       # Layout with collapsible sidebar
│   ├── partials/                       # Reusable components (icons, messages)
│   ├── accounts/                       # Auth pages
│   ├── patients/                       # Patient CRUD
│   ├── tasks/                          # Dashboard
│   ├── visits/                         # Visit detail + chat
│   └── documents/                      # Document management + PDF viewer
│
├── static/
│   ├── src/input.css                   # Tailwind source + component classes
│   └── css/tailwind.css               # Compiled output
│
└── media/                              # Uploaded files (gitignored)
    ├── patient_docs/
    ├── generated_reports/
    └── clinical_docs/
```

---

## Features

### AI Chat (Visit Workspace)
Doctors can ask natural-language questions about a patient during a visit. The RAG pipeline retrieves relevant chunks from uploaded documents, reranks them, and the LLM generates a grounded answer.

### Clinical Document Generation
Deterministic PDF generation (no LLM) for four document types:
- **Consultation Summary** — visit messages + doctor notes compiled into a structured summary
- **Prescription** — medication table with dose, route, frequency, duration, instructions
- **Medical Certificate** — patient info, diagnosis, leave dates, doctor signature
- **Referral Letter** — formal letter to a specialist with clinical findings and history

### Document Upload Pipeline
Uploaded PDFs go through: text extraction → section-aware chunking → PHI de-identification → embedding generation → pgvector storage. Chunks become searchable by the RAG pipeline.

### De-identification
Combines exact-match rules (names, MRNs) with Microsoft Presidio for PHI/PII detection. Clinical false positives (lab values, blood pressure readings) are protected.

---

## Running Tests

```bash
# Run all tests per app (known Django discovery issue with multiple labels)
python manage.py test accounts
python manage.py test patients
python manage.py test tasks
python manage.py test visits
python manage.py test documents
```

---

## Rebuilding Frontend

After any CSS changes:

```bash
npx tailwindcss -i static/src/input.css -o static/css/tailwind.css --minify
```
https://drive.google.com/drive/folders/1IL0Uuaq04ozy1WQlC04T9gHjn8tg0ery?usp=sharing
