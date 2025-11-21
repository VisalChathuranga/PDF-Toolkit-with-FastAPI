# 📄 PDF Processing Toolkit API

A powerful **Python + FastAPI** service to process PDF files with OCR, Markdown conversion, splitting, and merging.  
Supports **RapidOCR**, **Docling**, and is **fully open (no auth)** for easy integration.

---

## 🚀 Features

- ✅ **Local Directory Support**: Process files directly from your local folders
- ✅ Upload and manage PDFs per session
- ✅ OCR (text extraction with page-by-page or full document)
- ✅ Convert PDFs → **Markdown** (Docling, with optional OCR)
- ✅ Split PDFs by **range** or **specific pages**
- ✅ Merge multiple PDFs in any order
- ✅ Swagger & ReDoc auto-generated docs

---

## 📂 Project Structure

```
pdf-tool-kit/
├── pdfs/                 # Your input PDFs (default)
├── workspace/            # Auto-created output workspace (default)
├── commands.py           # Example CLI commands & Python usage
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
uvicorn pdf_api:app --reload --port 5005

# API Docs
http://localhost:5005/docs   # Swagger UI
http://localhost:5005/redoc  # ReDoc
```

---

## 🚀 Deployment & Microservice Usage

### 1. Running on a Server (e.g., "91 Server")

To make the API accessible to other servers (like your "Main Production Server"), you must run it with `--host 0.0.0.0`.

```bash
uvicorn pdf_api:app --host 0.0.0.0 --port 5005
```

### 2. Shared Paths / Network Drives

If you are calling this service from another server and passing `input_dir` / `output_dir`:

- **The paths must be visible to THIS service (the 91 server).**
- If the files are on the Main Server, you must mount that folder on the 91 Server (e.g., as a network drive `Z:/` or `/mnt/share`).
- Then pass the **mounted path** (e.g., `Z:/Input`) to the API.

---

## 📜 CURL Cheat Sheet

Here are the `curl` commands to integrate this service into your workflow.

### 1️⃣ Create Session (Define Paths)

Tell the service where to look for files and where to save them.

```bash
curl -X POST "http://192.168.1.91:5005/session/new" \
     -H "Content-Type: application/json" \
     -d '{
           "input_dir": "C:/Production/PDFs/Input",
           "output_dir": "C:/Production/PDFs/Output"
         }'
# Returns: {"session_id": "550e8400-e29b..."}
```

### 2️⃣ List Available Files

Check what PDFs are in the input directory.

```bash
curl "http://192.168.1.91:5005/session/<SESSION_ID>/files"
```

### 3️⃣ OCR (Image to Text)

Process a specific file found in the input directory.

**Option A: Full Text (One File)**

```bash
curl -X POST "http://192.168.1.91:5005/session/<SESSION_ID>/ocr?filename=scan.pdf&output=full"
```

**Option B: Per Page (Multiple Files)**

```bash
curl -X POST "http://192.168.1.91:5005/session/<SESSION_ID>/ocr?filename=scan.pdf&output=pages"
```

### 4️⃣ PDF to Markdown (Docling)

Convert a PDF to Markdown (great for LLM RAG).

```bash
# Standard
curl -X POST "http://192.168.1.91:5005/session/<SESSION_ID>/to-markdown?filename=doc.pdf&output=full"

# Force OCR (for scanned docs)
curl -X POST "http://192.168.1.91:5005/session/<SESSION_ID>/to-markdown?filename=scan.pdf&output=full&force_ocr=true"
```

### 5️⃣ Split Pages

**Split ALL pages to separate PDFs:**

```bash
curl -X POST "http://192.168.1.91:5005/session/<SESSION_ID>/split-pages?filename=doc.pdf"
```

**Extract Range (1-5) to New PDF:**

```bash
curl -X POST "http://192.168.1.91:5005/session/<SESSION_ID>/split-pages?filename=doc.pdf&page_range=1-5&combined=true"
```

### 6️⃣ Merge PDFs

Merge two files (must be in the input directory).

```bash
curl -X POST "http://192.168.1.91:5005/session/<SESSION_ID>/merge" \
     -H "Content-Type: application/json" \
     -d '{
           "filenames": ["part1.pdf", "part2.pdf"],
           "out_name": "final_merged.pdf"
         }'
```

### 7️⃣ Download Results (Optional)

If you didn't set an `output_dir`, or want to download the files over HTTP:

```bash
# Download everything as ZIP
curl -O -J "http://192.168.1.91:5005/session/<SESSION_ID>/download"

# Download specific file
curl -O -J "http://192.168.1.91:5005/session/<SESSION_ID>/download?name=final_merged.pdf"
```

---

## 🖥️ Example Python Client

```python
import requests

API_URL = "http://192.168.1.91:5005"

# 1. Setup Session
config = {
    "input_dir": "D:/Shared/In",
    "output_dir": "D:/Shared/Out"
}
sess = requests.post(f"{API_URL}/session/new", json=config).json()
sid = sess["session_id"]

# 2. Process
requests.post(f"{API_URL}/session/{sid}/ocr", params={"filename": "invoice.pdf"})
print("Done! Check D:/Shared/Out/ocr/")
```

---

## 📝 License

MIT © 2025 — Built for internal use 🚀

```

```
