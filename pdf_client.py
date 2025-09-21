'''
client_full.py
- Handshake with Basic -> get {session_id, access_token}
- Upload ALL PDFs from a folder (optionally recursive, in batches)
- Run: OCR (full & pages), MD (full & pages, with/without force_ocr), Split (all/range/specific, separate/combined), Merge
- Download ALL outputs as a ZIP

Requires: pip install requests
Run: python client_full.py
'''

import base64
import pathlib
import requests
from typing import Iterable, List, Tuple

# =========================
# CONFIG
# =========================
BASE = "http://localhost:8000"     # your API base
USER = "demo"                      # Basic auth username (from PDF_API_CLIENTS)
PASS = "demo"                      # Basic auth password

PDF_DIR   = pathlib.Path("./pdfs") # folder containing PDFs to upload
RECURSIVE = True                   # include subfolders?
BATCH_SIZE = 8                     # PDFs per upload request

# choose which uploaded file to target for per-file operations
PICK_FIRST_UPLOADED_FOR_DEMOS = True

# =========================
# HELPERS
# =========================
def basic_auth_header(user: str, pwd: str) -> dict:
    token = base64.b64encode(f"{user}:{pwd}".encode()).decode()
    return {"Authorization": f"Basic {token}"}

def bearer_header(jwt: str) -> dict:
    return {"Authorization": f"Bearer {jwt}"}

def find_pdfs(folder: pathlib.Path, recursive: bool = True) -> List[pathlib.Path]:
    if not folder.exists():
        raise FileNotFoundError(f"Folder not found: {folder}")
    pattern = "**/*.pdf" if recursive else "*.pdf"
    return sorted(p for p in folder.glob(pattern) if p.is_file() and p.suffix.lower() == ".pdf")

def batch(iterable: Iterable, n: int):
    buf = []
    for item in iterable:
        buf.append(item)
        if len(buf) == n:
            yield buf
            buf = []
    if buf:
        yield buf

def open_files_for_multipart(paths: List[pathlib.Path]) -> Tuple[List[Tuple[str, Tuple[str, object, str]]], List[object]]:
    files_param = []
    handles = []
    for p in paths:
        fh = open(p, "rb")
        handles.append(fh)
        files_param.append(("files", (p.name, fh, "application/pdf")))
    return files_param, handles

# =========================
# MAIN
# =========================
if __name__ == "__main__":
    # 1) Handshake (Basic) -> { session_id, access_token }
    r = requests.post(f"{BASE}/auth/handshake", headers=basic_auth_header(USER, PASS))
    r.raise_for_status()
    hs = r.json()
    session_id = hs["session_id"]
    token      = hs["access_token"]
    print(f"[handshake] session_id={session_id}")

    # 2) Discover PDFs in the folder (once)
    pdfs = find_pdfs(PDF_DIR, recursive=RECURSIVE)
    if not pdfs:
        raise SystemExit(f"No PDFs found in {PDF_DIR} (recursive={RECURSIVE})")
    print(f"[upload] found {len(pdfs)} PDFs under {PDF_DIR.resolve()} (recursive={RECURSIVE})")

    # 3) Upload in batches
    uploaded_total = 0
    for i, group in enumerate(batch(pdfs, BATCH_SIZE), start=1):
        files_param, handles = open_files_for_multipart(group)
        try:
            rr = requests.post(
                f"{BASE}/session/{session_id}/upload",
                headers=bearer_header(token),
                files=files_param,
                timeout=300,
            )
            rr.raise_for_status()
            uploaded_total += len(group)
            print(f"[upload][batch {i}] {len(group)} file(s) -> OK")
        finally:
            for h in handles:
                try: h.close()
                except: pass
    print(f"[upload] done: {uploaded_total} file(s) uploaded")

    # pick a file name to demonstrate per-file calls (first uploaded)
    target_pdf_name = pdfs[0].name if PICK_FIRST_UPLOADED_FOR_DEMOS else None
    if target_pdf_name:
        print(f"[demo] using target file: {target_pdf_name}")

    # =========================
    # OCR
    # =========================
    # a) one combined TXT (with page breakers)
    rr = requests.post(f"{BASE}/session/{session_id}/ocr",
                       headers=bearer_header(token),
                       params={"filename": target_pdf_name, "output": "full"},
                       timeout=3600)
    rr.raise_for_status()
    print("[ocr][full] saved:", rr.json().get("file_path"))

    # b) per-page TXT files
    rr = requests.post(f"{BASE}/session/{session_id}/ocr",
                       headers=bearer_header(token),
                       params={"filename": target_pdf_name, "output": "pages"},
                       timeout=3600)
    rr.raise_for_status()
    print("[ocr][pages] saved:", len(rr.json().get("file_paths", [])), "files")

    # =========================
    # Markdown (no OCR)
    # =========================
    rr = requests.post(f"{BASE}/session/{session_id}/to-markdown",
                       headers=bearer_header(token),
                       params={"filename": target_pdf_name, "output": "full"},
                       timeout=3600)
    rr.raise_for_status()
    print("[md][full] saved:", rr.json().get("file_path"))

    rr = requests.post(f"{BASE}/session/{session_id}/to-markdown",
                       headers=bearer_header(token),
                       params={"filename": target_pdf_name, "output": "pages"},
                       timeout=3600)
    rr.raise_for_status()
    print("[md][pages] saved:", len(rr.json().get("file_paths", [])), "files")

    # =========================
    # Markdown (force OCR inside Docling)
    # =========================
    rr = requests.post(f"{BASE}/session/{session_id}/to-markdown",
                       headers=bearer_header(token),
                       params={"filename": target_pdf_name, "force_ocr": "true", "output": "pages"},
                       timeout=7200)
    rr.raise_for_status()
    print("[md][pages][force_ocr] saved:", len(rr.json().get("file_paths", [])), "files")

    # =========================
    # Split pages
    # =========================
    # a) ALL pages -> separate PDFs
    rr = requests.post(f"{BASE}/session/{session_id}/split-pages",
                       headers=bearer_header(token),
                       params={"filename": target_pdf_name},   # no pages/range -> all separate
                       timeout=1200)
    rr.raise_for_status()
    print("[split][all->separate] files:", len(rr.json().get("output_files", [])))

    # b) RANGE (1–5) -> ONE combined PDF
    rr = requests.post(f"{BASE}/session/{session_id}/split-pages",
                       headers=bearer_header(token),
                       params={"filename": target_pdf_name, "page_range": "1-5", "combined": "true"},
                       timeout=600)
    rr.raise_for_status()
    print("[split][range->combined] out:", rr.json().get("output_files"))

    # c) specific pages (2, 7, 11, 15) -> separate PDFs
    rr = requests.post(f"{BASE}/session/{session_id}/split-pages",
                       headers=bearer_header(token),
                       params=[("filename", target_pdf_name)] + [("pages", p) for p in [2,7,11,15]],
                       timeout=600)
    rr.raise_for_status()
    print("[split][specific->separate] files:", len(rr.json().get("output_files", [])))

    # d) specific pages (2, 7, 11, 15) -> ONE combined PDF
    rr = requests.post(f"{BASE}/session/{session_id}/split-pages",
                       headers=bearer_header(token),
                       params=[("filename", target_pdf_name)] + [("pages", p) for p in [2,7,11,15]] + [("combined", "true")],
                       timeout=600)
    rr.raise_for_status()
    print("[split][specific->combined] out:", rr.json().get("output_files"))

    # =========================
    # Merge (example: merge first two uploaded PDFs if available)
    # =========================
    if len(pdfs) >= 2:
        names = [pdfs[0].name, pdfs[1].name]
        rr = requests.post(f"{BASE}/session/{session_id}/merge",
                           headers=bearer_header(token),
                           json={"filenames": names, "out_name": "merged.pdf"},
                           timeout=600)
        rr.raise_for_status()
        print("[merge] out:", rr.json().get("output_file"))

    # =========================
    # Download ALL outputs as ZIP
    # =========================
    out_zip = pathlib.Path("outputs.zip")
    with requests.get(f"{BASE}/session/{session_id}/download",
                      headers=bearer_header(token),
                      stream=True,
                      timeout=3600) as resp:
        resp.raise_for_status()
        with open(out_zip, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk: f.write(chunk)
    print("[download] saved ->", out_zip.resolve())
