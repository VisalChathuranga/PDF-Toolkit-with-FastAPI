# pdf_api.py
import os
import io
import uuid
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

import asyncio
from concurrent.futures import ThreadPoolExecutor
import tempfile
import datetime

# your existing toolkit
from main import PDFToolkit

# -----------------------------------------------------------------------------
# App setup
# -----------------------------------------------------------------------------
app = FastAPI(
    title="PDF Processing API",
    description="API for PDF operations: OCR, PDF→Markdown, split pages, merge",
    version="1.0.1",
)

# CORS (adjust in prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

executor = ThreadPoolExecutor(max_workers=os.cpu_count() or 4)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def get_kit(session_id: str) -> PDFToolkit:
    """Create a PDFToolkit instance bound to a session workspace."""
    base_dir = Path(f"/tmp/pdf_processing/{session_id}")
    return PDFToolkit(base_dir=base_dir)

async def _run_blocking(func):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, func)

def _safe_under(base: Path, target: Path) -> bool:
    try:
        return str(target.resolve()).startswith(str(base.resolve()))
    except Exception:
        return False

def _find_by_basename(root: Path, name: str) -> List[Path]:
    """Find files recursively by basename under root."""
    results: List[Path] = []
    for p in root.rglob("*"):
        if p.is_file() and p.name == name:
            results.append(p)
    return results

def _pick_best_match(root: Path, candidates: List[Path]) -> Tuple[Optional[Path], List[Path]]:
    """Prefer files under 'output/' and then by latest mtime."""
    if not candidates:
        return None, []
    # prefer output/*
    output_candidates = [c for c in candidates if (root / "output") in c.parents]
    pool = output_candidates or candidates
    best = max(pool, key=lambda p: p.stat().st_mtime)
    return best, candidates

def _zip_outputs(base: Path) -> Path:
    """Create a zip of the session outputs. If outputs empty, zip whole base."""
    out_dir = base / "output"
    target_dir = out_dir if out_dir.exists() and any(out_dir.rglob("*")) else base
    zip_name = f"download_{datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}"
    zip_base = base / zip_name
    archive_path = shutil.make_archive(str(zip_base), "zip", root_dir=target_dir)
    return Path(archive_path)

# -----------------------------------------------------------------------------
# Sessions
# -----------------------------------------------------------------------------
@app.post("/session/start")
async def start_session():
    session_id = str(uuid.uuid4())
    _ = get_kit(session_id)  # ensure folders
    return {"session_id": session_id}

@app.delete("/session/{session_id}")
async def cleanup_session(session_id: str):
    try:
        base_dir = Path(f"/tmp/pdf_processing/{session_id}")
        if base_dir.exists():
            shutil.rmtree(base_dir)
        return {"message": f"Session {session_id} cleaned up"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -----------------------------------------------------------------------------
# Upload
# -----------------------------------------------------------------------------
@app.post("/session/{session_id}/upload")
async def upload_files(session_id: str, files: List[UploadFile] = File(...)):
    try:
        kit = get_kit(session_id)
        saved_paths = []
        for file in files:
            if file.content_type not in ("application/pdf", "application/x-pdf"):
                raise HTTPException(status_code=400, detail=f"Only PDF files allowed: {file.filename}")
            dst = kit.paths["input"] / file.filename
            dst.parent.mkdir(parents=True, exist_ok=True)
            with open(dst, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            saved_paths.append(str(dst))
        return {"message": f"Uploaded {len(saved_paths)} file(s)", "files": saved_paths}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -----------------------------------------------------------------------------
# OCR
# -----------------------------------------------------------------------------
@app.post("/session/{session_id}/ocr")
async def ocr_pdf(
    session_id: str,
    filename: Optional[str] = None,
    preprocess: bool = True,
    output: str = "full",  # "full" or "pages"
):
    try:
        kit = get_kit(session_id)
        text_or_pages, path_or_paths = await _run_blocking(
            lambda: kit.ocr_pdf(pdf_path=filename, preprocess=preprocess, output=output)
        )
        if output == "full":
            return {"text": text_or_pages, "file_path": str(path_or_paths) if path_or_paths else None}
        else:
            return {"pages": text_or_pages, "file_paths": [str(p) for p in (path_or_paths or [])]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -----------------------------------------------------------------------------
# PDF → Markdown
# -----------------------------------------------------------------------------
@app.post("/session/{session_id}/to-markdown")
async def to_markdown(
    session_id: str,
    filename: Optional[str] = None,
    force_ocr: bool = False,
    output: str = "full",  # "full" or "pages"
):
    try:
        kit = get_kit(session_id)
        md_or_pages, path_or_paths = await _run_blocking(
            lambda: kit.pdf_to_markdown(pdf_path=filename, force_ocr=force_ocr, output=output)
        )
        if output == "full":
            return {"markdown": md_or_pages, "file_path": str(path_or_paths) if path_or_paths else None}
        else:
            return {"pages": md_or_pages, "file_paths": [str(p) for p in (path_or_paths or [])]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -----------------------------------------------------------------------------
# Split pages
# -----------------------------------------------------------------------------
@app.post("/session/{session_id}/split-pages")
async def split_pages(
    session_id: str,
    filename: Optional[str] = None,
    pages: Optional[List[int]] = None,   # e.g., [2,7,11,15]
    page_range: Optional[str] = None,    # e.g., "1-5"
    combined: bool = False,              # one combined PDF if True, else separate
):
    try:
        kit = get_kit(session_id)
        outputs = await _run_blocking(
            lambda: kit.split_pages(pdf_path=filename, pages=pages, page_range=page_range, combined=combined)
        )
        return {"output_files": [str(p) for p in outputs]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -----------------------------------------------------------------------------
# Merge
# -----------------------------------------------------------------------------
@app.post("/session/{session_id}/merge")
async def merge_pdfs(
    session_id: str,
    filenames: List[str],
    out_name: str = "merged.pdf",
):
    try:
        kit = get_kit(session_id)
        outp = await _run_blocking(lambda: kit.merge_pdfs(pdf_files=filenames, out_name=out_name))
        return {"output_file": str(outp)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -----------------------------------------------------------------------------
# Download
#   - Default (no name): zip ALL outputs and return the archive.
#   - With ?name=<filename>: find by basename anywhere in session (prefer output/, latest mtime).
# -----------------------------------------------------------------------------
@app.get("/session/{session_id}/download")
async def download(
    session_id: str,
    name: Optional[str] = Query(default=None, description="Just the filename (e.g., 'file.pdf'). Omit to download all outputs as a zip."),
):
    kit = get_kit(session_id)
    base = kit.paths["base"].resolve()

    if name is None:
        # zip entire output (or full base if output is empty)
        try:
            zip_path = _zip_outputs(base)
            return FileResponse(path=zip_path, filename=zip_path.name, media_type="application/zip")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create zip: {e}")

    # name provided: search by basename
    candidates = _find_by_basename(base, name)
    best, all_matches = _pick_best_match(base, candidates)
    if best is None:
        raise HTTPException(status_code=404, detail=f"No file named '{name}' found in session outputs")

    # add a hint header if there were multiple matches
    headers = {}
    if len(all_matches) > 1:
        rels = [str(p.resolve().relative_to(base)) for p in all_matches]
        headers["X-Download-Note"] = f"Multiple matches for {name}; returning most recent from preference set. Candidates: {', '.join(rels[:5])}{' ...' if len(rels)>5 else ''}"

    return FileResponse(
        path=str(best),
        filename=best.name,
        media_type="application/octet-stream",
        headers=headers,
    )

# -----------------------------------------------------------------------------
# Local run
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
