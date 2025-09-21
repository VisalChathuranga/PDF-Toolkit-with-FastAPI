# 📄 PDF Processing Toolkit API

A powerful **Python + FastAPI** service to process PDF files with OCR, Markdown conversion, splitting, and merging.  
Supports **RapidOCR**, **Docling**, and includes **Basic + JWT Authentication** for security.

---

## 🚀 Features

- ✅ Upload and manage PDFs per session  
- ✅ OCR (text extraction with page-by-page or full document)  
- ✅ Convert PDFs → **Markdown** (Docling, with optional OCR)  
- ✅ Split PDFs by **range** or **specific pages**  
- ✅ Merge multiple PDFs in any order  
- ✅ Secure API with **Basic Auth** + **JWT**  
- ✅ Swagger & ReDoc auto-generated docs  

---

## 📂 Project Structure

```
pdf-tool-kit/
├── pdfs/                 # Your input PDFs
├── workspace/            # Auto-created output workspace
├── auth.py               # Authentication (Basic + JWT)
├── commands.py           # Example CLI commands (optional)
├── main.py               # Core PDFToolkit class (processing logic)
├── pdf_api.py            # FastAPI server (exposes endpoints)
├── pdf_client.py         # Example Python client
├── requirements.txt      # Python dependencies
├── README.md             # This file
└── .env                  # Optional environment variables
```

---

## ⚙️ Installation

```bash
# 1) Create env
conda create -n pdf_toolkit python=3.11 -y
conda activate pdf_toolkit

# 2) Install dependencies
pip install -r requirements.txt

# 3) Run API
uvicorn pdf_api:app --reload

# API Docs
http://localhost:8000/docs   # Swagger UI
http://localhost:8000/redoc  # ReDoc
```

---

## 🔑 Authentication

- First, authenticate with **Basic Auth** → receive `session_id` + `JWT`  
- Then, use the `JWT` (`Bearer token`) for all subsequent requests  
- Sessions **expire after 1 hour** (configurable)

Example (Basic Auth header):  
```
Authorization: Basic base64(username:password)
```

Example (JWT Bearer header):  
```
Authorization: Bearer <your_token>
```

---

## 🖥️ Example Client

```python
from pdf_client import run_demo

# This will:
# 1. Authenticate
# 2. Upload all PDFs in ./pdfs/
# 3. Run OCR, Markdown, Split, Merge
# 4. Download results as outputs.zip

run_demo()
```

---

## 🔧 Example API Usage (Python Client)

```python
# OCR
full_txt, full_txt_path   = kit.ocr_pdf(output="full")    # one TXT with page breakers
pages_txt, page_txt_paths = kit.ocr_pdf(output="pages")   # per-page TXT files

# Markdown (no OCR)
full_md, full_md_path     = kit.pdf_to_markdown(output="full")
pages_md, page_md_paths   = kit.pdf_to_markdown(output="pages")

# Markdown (force OCR inside Docling)
md_pages_ocr, md_paths_ocr = kit.pdf_to_markdown(force_ocr=True, output="pages")

# Split pages
outs_all_separate   = kit.split_pages()
outs_range_combined = kit.split_pages(page_range="1-5", combined=True)
outs_specific_sep   = kit.split_pages(pages=[2, 7, 11, 15])
outs_specific_comb  = kit.split_pages(pages=[2, 7, 11, 15], combined=True)

# Merge
merged = kit.merge_pdfs(["a.pdf", "b.pdf"], out_name="merged.pdf")
```

---

## 📦 Download Results

- **Default** → `/download` returns **all outputs** as `.zip`  
- **Specific file** → `/download?name=file.pdf` returns the chosen file  

---

## 🛡️ Environment Variables

Set in `.env` or system:  

```bash
# Allowed clients (username/password pairs)
PDF_API_CLIENTS='{"demo":"demo","myapp":"supersecret"}'

# Token lifetime (minutes)
PDF_API_TOKEN_TTL_MIN=60
```

---

## 📝 License

MIT © 2025 — Built for internal use 🚀
