# pdf_api.py
import os
import shutil
import uuid
from pathlib import Path
from typing import List, Optional, Dict

from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import asyncio
from concurrent.futures import ThreadPoolExecutor

# toolkit
from main import PDFToolkit

app = FastAPI(
    title="PDF Processing API",
    description="API for PDF operations: OCR, PDF→Markdown, split pages, merge",
    version="1.5.0 (local-paths)",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

executor = ThreadPoolExecutor(max_workers=os.cpu_count() or 4)

# ----------------------- SESSION STATE -----------------------

from datetime import datetime

# ... (imports)

# ----------------------- SESSION STATE -----------------------

class SessionConfig(BaseModel):
    input_dir: Optional[str] = None
    output_dir: Optional[str] = None
    created_at: datetime = None

SESSIONS: Dict[str, SessionConfig] = {}

def get_kit(session_id: str) -> PDFToolkit:
    base_dir = Path(f"/tmp/pdf_processing/{session_id}")
    config = SESSIONS.get(session_id)
    
    if config:
        return PDFToolkit(
            base_dir=base_dir,
            input_dir=config.input_dir,
            output_dir=config.output_dir
        )
    return PDFToolkit(base_dir=base_dir)

async def _run_blocking(func):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, func)

def _find_by_basename(root: Path, name: str):
    return [p for p in root.rglob("*") if p.is_file() and p.name == name]

def _pick_best_match(root: Path, candidates: List[Path]):
    if not candidates:
        return None, []
    output_candidates = [c for c in candidates if (root / "output") in c.parents]
    pool = output_candidates or candidates
    best = max(pool, key=lambda p: p.stat().st_mtime)
    return best, candidates

def _zip_outputs(base: Path) -> Path:
    out_dir = base / "output"
    target_dir = out_dir if out_dir.exists() and any(out_dir.rglob("*")) else base
    zip_name = "download_all"
    archive_path = shutil.make_archive(str(base / zip_name), "zip", root_dir=target_dir)
    return Path(archive_path)

# ----------------------- SESSION -----------------------

@app.post("/session/new", tags=["session"])
async def create_session(config: Optional[SessionConfig] = None):
    """
    Create a new session ID. 
    Optionally pass 'input_dir' and 'output_dir' to use existing local folders.
    """
    session_id = str(uuid.uuid4())
    now = datetime.now()
    
    if config:
        config.created_at = now
        SESSIONS[session_id] = config
    else:
        SESSIONS[session_id] = SessionConfig(created_at=now)
    return {"session_id": session_id, "started_at": now.isoformat()}

@app.get("/session/{session_id}/status", tags=["session"])
async def get_session_status(session_id: str):
    """
    Get session duration and status.
    """
    config = SESSIONS.get(session_id)
    if not config:
        raise HTTPException(status_code=404, detail="Session not found")
    
    duration = datetime.now() - config.created_at
    return {
        "session_id": session_id,
        "active": True,
        "started_at": config.created_at.isoformat(),
        "duration_seconds": duration.total_seconds(),
        "duration_human": str(duration).split('.')[0]  # HH:MM:SS
    }

@app.get("/session/{session_id}/files", tags=["session"])
async def list_files(session_id: str):
    """
    List PDF files in the session's input directory.
    """
    try:
        kit = get_kit(session_id)
        files = [p.name for p in kit._list_input_pdfs()]
        return {"files": files, "input_dir": str(kit.paths["input"])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/session/{session_id}", tags=["session"])
async def cleanup_session(session_id: str):
    """
    Stop session and clean up temporary files.
    """
    try:
        # Remove from memory
        if session_id in SESSIONS:
            del SESSIONS[session_id]
            
        # Remove temp files
        base_dir = Path(f"/tmp/pdf_processing/{session_id}")
        if base_dir.exists():
            shutil.rmtree(base_dir)
            
        return {"message": f"Session {session_id} stopped and cleaned up"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------- OPS ------------------------

@app.post("/session/{session_id}/upload", tags=["io"])
async def upload_files(
    session_id: str,
    files: List[UploadFile] = File(...),
):
    try:
        kit = get_kit(session_id)
        saved_paths = []
        for file in files:
            if file.content_type not in ("application/pdf", "application/x-pdf", "application/octet-stream"):
                if not file.filename.lower().endswith(".pdf"):
                    raise HTTPException(status_code=400, detail=f"Only PDF files allowed: {file.filename}")
            dst = kit.paths["input"] / file.filename
            dst.parent.mkdir(parents=True, exist_ok=True)
            with open(dst, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            saved_paths.append(str(dst))
        return {"message": f"Uploaded {len(saved_paths)} file(s)", "files": saved_paths}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/session/{session_id}/ocr", tags=["ops"])
async def ocr_pdf(
    session_id: str,
    filename: Optional[str] = None,
    preprocess: bool = True,
    output: str = "full",
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

@app.post("/session/{session_id}/to-markdown", tags=["ops"])
async def to_markdown(
    session_id: str,
    filename: Optional[str] = None,
    force_ocr: bool = False,
    output: str = "full",
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

@app.post("/session/{session_id}/split-pages", tags=["ops"])
async def split_pages(
    session_id: str,
    filename: Optional[str] = None,
    pages: Optional[List[int]] = None,
    page_range: Optional[str] = None,
    combined: bool = False,
):
    try:
        kit = get_kit(session_id)
        outputs = await _run_blocking(
            lambda: kit.split_pages(pdf_path=filename, pages=pages, page_range=page_range, combined=combined)
        )
        return {"output_files": [str(p) for p in outputs]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/session/{session_id}/merge", tags=["ops"])
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

@app.get("/session/{session_id}/download", tags=["io"])
async def download(
    session_id: str,
    name: Optional[str] = Query(default=None, description="Just the filename (e.g., 'file.pdf'). Omit to download all outputs as a zip."),
):
    kit = get_kit(session_id)
    base = kit.paths["base"].resolve()

    if name is None:
        try:
            zip_path = _zip_outputs(base)
            return FileResponse(path=zip_path, filename=zip_path.name, media_type="application/zip")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create zip: {e}")

    candidates = _find_by_basename(base, name)
    best, all_matches = _pick_best_match(base, candidates)
    if best is None:
        raise HTTPException(status_code=404, detail=f"No file named '{name}' found in session outputs")

    headers = {}
    if len(all_matches) > 1:
        try:
            rels = [str(p.resolve().relative_to(base)) for p in all_matches]
            headers["X-Download-Note"] = f"Multiple matches for {name}; returning most recent. Candidates: {', '.join(rels[:5])}{' ...' if len(rels)>5 else ''}"
        except Exception:
            pass

    return FileResponse(path=str(best), filename=best.name, media_type="application/octet-stream", headers=headers)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5005)
