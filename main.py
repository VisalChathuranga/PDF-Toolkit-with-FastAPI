from __future__ import annotations

import argparse
import io
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple, Union

import logging
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("pdf_toolkit")

# PDF + imaging
from pypdf import PdfReader, PdfWriter
import fitz  # PyMuPDF
from PIL import Image

# Docling
from docling.document_converter import DocumentConverter

# OCR (RapidOCR only)
from rapidocr_onnxruntime import RapidOCR

# Optional (used for small image cleanups / numpy conversion)
import numpy as np
import cv2


class PDFToolkit:
    """
    Workspace-first utilities: upload, OCR (RapidOCR), PDF->Markdown, split, merge.

    Convenience behavior:
      • If there's exactly ONE PDF in <base>/input, methods accept NO filename:
          kit.ocr_pdf(); kit.pdf_to_markdown(); kit.split_pages()
      • If multiple PDFs exist, pass the filename:
          kit.ocr_pdf("a.pdf"); kit.split_pages("a.pdf")
    """

    def __init__(
        self,
        base_dir: Path | str = "workspace",
        input_dir: Path | str = None,
        output_dir: Path | str = None,
        dpi: int = 300
    ):
        self.base_dir = Path(base_dir)
        self.input_dir = Path(input_dir) if input_dir else self.base_dir / "input"
        self.output_dir = Path(output_dir) if output_dir else self.base_dir / "output"
        self.dpi = dpi
        self.paths = self._setup_paths()

    def _setup_paths(self) -> dict:
        """
        Ensure the expected directory layout exists and return useful paths.
        """
        paths = {
            "base": self.base_dir,
            "input": self.input_dir,
            "output": self.output_dir,
            "ocr_out": self.output_dir / "ocr",
            "md_out": self.output_dir / "markdown",
            "split_out": self.output_dir / "splits",
            "merge_out": self.output_dir / "merged",
            "temp": self.base_dir / "temp",
        }
        for p in paths.values():
            if isinstance(p, Path):
                p.mkdir(parents=True, exist_ok=True)
        return paths

    # ---- helpers ----

    def _list_input_pdfs(self) -> List[Path]:
        return sorted(self.paths["input"].glob("*.pdf"))

    def _pick_single_pdf(self) -> Path:
        pdfs = self._list_input_pdfs()
        if not pdfs:
            raise FileNotFoundError(
                f"No PDFs in {self.paths['input']}. Use ingest(...) first."
            )
        if len(pdfs) > 1:
            names = ", ".join(p.name for p in pdfs[:10])
            more = "" if len(pdfs) <= 10 else f" (+{len(pdfs)-10} more)"
            raise ValueError(
                f"Multiple PDFs found in {self.paths['input']}: {names}{more}. "
                f"Please specify a filename."
            )
        return pdfs[0]

    def _resolve_input_path(self, p: Optional[Union[str, Path]]) -> Path:
        """
        Resolve to a real PDF path.
        - If p is None: pick the single PDF in workspace/input (or raise if 0/ >1)
        - If p exists: use it
        - Else: try workspace/input/<p>
        """
        if p is None:
            return self._pick_single_pdf()

        p = Path(p)
        if p.exists():
            return p

        candidate = (self.paths["input"] / p).resolve()
        if candidate.exists():
            return candidate

        candidate2 = (self.paths["input"] / p.name).resolve()
        if candidate2.exists():
            return candidate2

        raise FileNotFoundError(
            f"Could not find '{p}'. Tried '{p}' and '{self.paths['input'] / p}'."
        )

    # 1) "Upload" (copy / normalize) -------------------------------------------------

    def ingest(self, pdf_files: Sequence[Union[str, Path]]) -> List[Path]:
        """
        Copy input PDFs into workspace/input and return their new paths.
        """
        accepted: List[Path] = []
        for f in pdf_files:
            src = Path(f)
            if not src.exists() or src.suffix.lower() != ".pdf":
                log.warning(f"Skipping non-existent or non-PDF: {src}")
                continue
            dst = self.paths["input"] / src.name
            if src.resolve() == dst.resolve():
                accepted.append(dst)
                continue
            dst.write_bytes(src.read_bytes())
            accepted.append(dst)
            log.info(f"Ingested -> {dst}")
        return accepted

    # 2) OCR (RapidOCR only) ---------------------------------------------------------

    @staticmethod
    def _render_pdf_to_images(pdf_path: Path, dpi: int = 300) -> List[np.ndarray]:
        """
        Render each PDF page to an RGB numpy array using PyMuPDF.
        """
        images: List[np.ndarray] = []
        with fitz.open(pdf_path) as doc:
            for page in doc:
                pix = page.get_pixmap(dpi=dpi, alpha=False)  # 300 dpi recommended
                img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
                images.append(np.array(img))
        return images

    @staticmethod
    def _postprocess_for_ocr(img: np.ndarray) -> np.ndarray:
        """
        Light cleanup to help OCR: grayscale + denoise + threshold.
        """
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        filt = cv2.bilateralFilter(gray, d=7, sigmaColor=50, sigmaSpace=50)
        th = cv2.adaptiveThreshold(
            filt, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10
        )
        return th

    def ocr_pdf(
        self,
        pdf_path: Optional[Union[str, Path]] = None,
        preprocess: bool = True,
        write_txt: bool = True,
        out_name: Optional[str] = None,
        output: str = "full",  # "full" | "pages"
    ) -> Tuple[Union[str, List[str]], Optional[Union[Path, List[Path]]]]:
        """
        OCR a (scanned) PDF with RapidOCR.

        output:
          - "full"  (default): returns a single string (with page breakers) and writes one file.
          - "pages": returns a list[str] (one per page) and writes one file per page.

        Returns (text_or_pages, saved_path_or_paths).
        """
        pdf_path = self._resolve_input_path(pdf_path)
        images = self._render_pdf_to_images(pdf_path, dpi=self.dpi)
        if preprocess:
            images = [self._postprocess_for_ocr(im) for im in images]

        ocr = RapidOCR()
        page_texts: List[str] = []
        for idx, im in enumerate(images, start=1):
            result, _ = ocr(im)  # list of [box, text, score]
            lines = [r[1] for r in result] if result else []
            page_texts.append("\n".join(lines).strip())

        if output not in {"full", "pages"}:
            raise ValueError("output must be 'full' or 'pages'")

        out_dir = self.paths["ocr_out"]
        out_dir.mkdir(parents=True, exist_ok=True)

        if output == "pages":
            saved_paths: List[Path] = []
            for i, txt in enumerate(page_texts, start=1):
                outp = out_dir / f"{pdf_path.stem}_p{i:04d}.rapidocr.txt"
                if write_txt:
                    outp.write_text(txt, encoding="utf-8")
                saved_paths.append(outp)
            return page_texts, (saved_paths if write_txt else None)

        # output == "full"
        breaker_joined = []
        for i, txt in enumerate(page_texts, start=1):
            breaker_joined.append(f"--------- Page {i} ---------\n{txt}".rstrip())
        full_text = "\n\n".join(breaker_joined).strip()

        saved_path = None
        if write_txt:
            out = out_dir / (out_name or (pdf_path.stem + ".rapidocr.txt"))
            out.write_text(full_text, encoding="utf-8")
            saved_path = out
            log.info(f"OCR text saved -> {out}")

        return full_text, saved_path

    # 3) PDF -> Markdown with Docling ------------------------------------------------

    def _make_docling_converter(
        self,
        force_ocr: bool = False,
    ) -> DocumentConverter:
        """
        Build a DocumentConverter with your requested PdfPipelineOptions:
            PdfPipelineOptions(
                generate_page_images=False,
                images_scale=1.00,
                do_ocr=False,
                do_picture_description=False,
                ocr_options=RapidOcrOptions(),
                picture_description_options=smolvlm_picture_description,
                extract_tables=Table,
                table_as_markdown=Table
            )
        If force_ocr=True, boolean flags are flipped to True (e.g., do_ocr, do_picture_description,
        generate_page_images).
        """
        # imports guarded for version differences
        from docling.datamodel.base_models import InputFormat
        from docling.document_converter import PdfFormatOption as _PdfFmt  # try modern name
        try:
            PdfFmt = _PdfFmt
        except Exception:
            from docling.document_converter import PdfFormatOptions as _PdfFmt  # fallback
            PdfFmt = _PdfFmt

        # Try to import option classes; ignore if not available in your docling version
        try:
            from docling.datamodel.pipeline_options import (
                PdfPipelineOptions,
                RapidOcrOptions,
            )
        except Exception as e:
            raise RuntimeError(
                "Your docling version does not expose expected pipeline options. "
                "Please upgrade docling."
            ) from e

        # Optional/advanced knobs (best-effort; not all builds expose these)
        smolvlm_picture_description = None  # placeholder; set your model/config if available
        Table = True  # placeholder; any truthy value to indicate 'enable' when supported

        pipe = PdfPipelineOptions()

        # Defaults per your spec
        # (use hasattr to stay robust to version differences)
        if hasattr(pipe, "generate_page_images"):
            pipe.generate_page_images = False
        if hasattr(pipe, "images_scale"):
            pipe.images_scale = 1.00
        if hasattr(pipe, "do_ocr"):
            pipe.do_ocr = False
        if hasattr(pipe, "do_picture_description"):
            pipe.do_picture_description = False
        if hasattr(pipe, "ocr_options"):
            try:
                pipe.ocr_options = RapidOcrOptions()
            except Exception:
                pass
        if hasattr(pipe, "picture_description_options") and smolvlm_picture_description is not None:
            pipe.picture_description_options = smolvlm_picture_description
        if hasattr(pipe, "extract_tables"):
            pipe.extract_tables = Table
        if hasattr(pipe, "table_as_markdown"):
            pipe.table_as_markdown = Table

        # Flip relevant booleans when forcing OCR
        if force_ocr:
            if hasattr(pipe, "generate_page_images"):
                pipe.generate_page_images = True
            if hasattr(pipe, "do_ocr"):
                pipe.do_ocr = True
            if hasattr(pipe, "do_picture_description"):
                pipe.do_picture_description = True

        return DocumentConverter(format_options={InputFormat.PDF: PdfFmt(pipeline_options=pipe)})

    def _docling_convert_one(self, pdf_or_page_path: Path, force_ocr: bool) -> str:
        converter = self._make_docling_converter(force_ocr=force_ocr)
        return converter.convert(pdf_or_page_path).document.export_to_markdown()

    def pdf_to_markdown(
        self,
        pdf_path: Optional[Union[str, Path]] = None,
        force_ocr: bool = False,
        output: str = "full",  # "full" | "pages"
        out_name: Optional[str] = None,
    ) -> Tuple[Union[str, List[str]], Union[Path, List[Path]]]:
        """
        Convert PDF to Markdown via Docling.

        output:
          - "full"  (default): returns a single markdown string (with page breakers) and writes one file.
          - "pages": returns list[str] (one per page) and writes one .md per page.

        Returns (md_or_pages, saved_path_or_paths).
        """
        src_pdf = self._resolve_input_path(pdf_path)

        # We produce page-aware markdown by converting each page separately
        # (robust way to ensure page markers & "pages" output work across Docling versions).
        reader = PdfReader(str(src_pdf))
        total = len(reader.pages)
        md_pages: List[str] = []
        page_paths: List[Path] = []

        temp_dir = self.paths["temp"]
        md_dir = self.paths["md_out"]
        md_dir.mkdir(parents=True, exist_ok=True)

        for i in range(total):
            # Write a one-page temp PDF
            tmp_pdf_path = temp_dir / f"{src_pdf.stem}_tmp_p{i+1:04d}.pdf"
            writer = PdfWriter()
            writer.add_page(reader.pages[i])
            with tmp_pdf_path.open("wb") as f:
                writer.write(f)

            md_txt = self._docling_convert_one(tmp_pdf_path, force_ocr=force_ocr)
            md_pages.append(md_txt)

            # Persist per-page .md when output="pages"
            page_md_path = md_dir / f"{src_pdf.stem}_p{i+1:04d}.md"
            page_paths.append(page_md_path)

        if output not in {"full", "pages"}:
            raise ValueError("output must be 'full' or 'pages'")

        if output == "pages":
            saved_paths: List[Path] = []
            for i, md_txt in enumerate(md_pages, start=1):
                outp = md_dir / f"{src_pdf.stem}_p{i:04d}.md"
                outp.write_text(md_txt, encoding="utf-8")
                saved_paths.append(outp)
            return md_pages, saved_paths

        # output == "full"
        breaker_joined = []
        for i, md_txt in enumerate(md_pages, start=1):
            breaker_joined.append(f"--------- Page {i} ---------\n\n{md_txt}".rstrip())

        full_md = "\n\n".join(breaker_joined).strip()
        out = md_dir / (out_name or (src_pdf.stem + ".md"))
        out.write_text(full_md, encoding="utf-8")
        log.info(f"Markdown saved -> {out}")
        return full_md, out

    # 4) Splitting -------------------------------------------------------------------

    def split_pages(
        self,
        pdf_path: Optional[Union[str, Path]] = None,
        pages: Optional[Iterable[int]] = None,
        page_range: Optional[str] = None,
        combined: bool = False,
    ) -> List[Path]:
        """
        Split selected (or all) pages into PDFs.

        Defaults:
          - If no pages/range provided: split ALL pages into SEPARATE PDFs.
          - You can pass either:
              • page_range: e.g. "1-5"  (inclusive)
              • pages:      e.g. [2, 7, 11, 15]
          - combined=False  -> one PDF per page (separate files)
          - combined=True   -> a single combined PDF containing the selected pages (in order)

        Pages are 1-based.
        """
        src = self._resolve_input_path(pdf_path)
        reader = PdfReader(str(src))
        total = len(reader.pages)

        # Build target page list
        targets: List[int]
        if page_range:
            rng = page_range.replace(" ", "")
            if "-" not in rng:
                raise ValueError('page_range must look like "start-end", e.g., "1-5"')
            start_s, end_s = rng.split("-", 1)
            start_i = int(start_s)
            end_i = int(end_s)
            if start_i < 1 or end_i < 1 or start_i > end_i:
                raise ValueError("Invalid page_range values")
            targets = list(range(start_i, min(end_i, total) + 1))
        elif pages:
            targets = sorted(set(int(p) for p in pages if 1 <= int(p) <= total))
            if not targets:
                raise ValueError("No valid page numbers were provided")
        else:
            targets = list(range(1, total + 1))  # default: all pages

        out_dir = self.paths["split_out"]
        out_dir.mkdir(parents=True, exist_ok=True)

        outputs: List[Path] = []
        if combined:
            writer = PdfWriter()
            for p in targets:
                writer.add_page(reader.pages[p - 1])
            # create a nice suffix
            if page_range:
                suffix = f"{targets[0]:04d}-{targets[-1]:04d}"
            else:
                suffix = "sel_" + "_".join(f"{p:02d}" for p in targets[:10])
                if len(targets) > 10:
                    suffix += f"_plus{len(targets)-10}"
            out = out_dir / f"{src.stem}_pages_{suffix}.pdf"
            with out.open("wb") as f:
                writer.write(f)
            outputs.append(out)
            log.info(f"Combined split -> {out} (pages {targets})")
            return outputs

        # separate files per page
        for p in targets:
            writer = PdfWriter()
            writer.add_page(reader.pages[p - 1])
            out = out_dir / f"{src.stem}_p{p:04d}.pdf"
            with out.open("wb") as f:
                writer.write(f)
            outputs.append(out)
            log.info(f"Split page -> {out}")
        return outputs

    # 5) Merging ---------------------------------------------------------------------

    def merge_pdfs(
        self, pdf_files: Sequence[Union[str, Path]], out_name: str = "merged.pdf"
    ) -> Path:
        """
        Merge multiple PDFs in the given order. File names can be relative
        to <workspace>/input.
        """
        out_dir = self.paths["merge_out"]
        out = out_dir / out_name
        writer = PdfWriter()
        for f in pdf_files:
            resolved = self._resolve_input_path(f)
            writer.append(str(resolved))
            log.info(f"Appended: {resolved.name}")
        with out.open("wb") as fp:
            writer.write(fp)
        log.info(f"Merged -> {out}")
        return out


# ---------- CLI (optional) ----------
# Mirrors the single-file default and the new output modes.

def build_cli() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="PDF Toolkit (upload, OCR, markdown, split, merge)")
    p.add_argument("--base", default="workspace", help="Base workspace directory (default: workspace)")
    sub = p.add_subparsers(dest="cmd", required=True)

    up = sub.add_parser("ingest", help="Copy PDFs into <base>/input")
    up.add_argument("files", nargs="+", help="PDF files to ingest")

    ocr = sub.add_parser("ocr", help="OCR a PDF (RapidOCR only)")
    ocr.add_argument("pdf", nargs="?", default=None, help="PDF filename or path (omit if only one)")
    ocr.add_argument("--output", choices=["full", "pages"], default="full")
    ocr.add_argument("--no-pre", action="store_true", help="disable preprocessing")

    md = sub.add_parser("to-md", help="Convert PDF to Markdown via Docling")
    md.add_argument("pdf", nargs="?", default=None, help="PDF filename or path (omit if only one)")
    md.add_argument("--output", choices=["full", "pages"], default="full")
    md.add_argument("--force-ocr", action="store_true", help="If set, flips pipeline booleans to True")

    # removed split-n
    spp = sub.add_parser("split-pages", help="Split selected (or all) pages")
    spp.add_argument("--pdf", default=None, help="PDF filename or path (omit if only one)")
    spp.add_argument("--pages", nargs="*", type=int, help="Explicit 1-based pages, e.g. 2 7 11 15")
    spp.add_argument("--range", dest="page_range", default=None, help='Inclusive page range, e.g. "1-5"')
    spp.add_argument("--combined", action="store_true", help="Combine selected pages into one PDF")

    mg = sub.add_parser("merge", help="Merge PDFs in order")
    mg.add_argument("files", nargs="+", help="PDF filenames or paths to merge")
    mg.add_argument("--out", default="merged.pdf")

    return p


def main():
    args = build_cli().parse_args()
    kit = PDFToolkit(base_dir=args.base)

    if args.cmd == "ingest":
        kit.ingest(args.files)

    elif args.cmd == "ocr":
        txt_or_pages, paths = kit.ocr_pdf(
            args.pdf,
            preprocess=not args.no_pre,
            output=args.output,
        )
        log.info(f"OCR output saved: {paths}")

    elif args.cmd == "to-md":
        md_or_pages, paths = kit.pdf_to_markdown(
            args.pdf,
            force_ocr=args.force_ocr,
            output=args.output,
        )
        log.info(f"Markdown saved: {paths}")

    elif args.cmd == "split-pages":
        outs = kit.split_pages(
            pdf_path=args.pdf,
            pages=args.pages,
            page_range=args.page_range,
            combined=args.combined,
        )
        log.info(f"Created {len(outs)} PDF file(s)")

    elif args.cmd == "merge":
        out = kit.merge_pdfs(args.files, out_name=args.out)
        log.info(f"Merged file: {out}")


if __name__ == "__main__":
    main()
