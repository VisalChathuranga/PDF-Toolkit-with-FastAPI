from main import PDFToolkit
from pathlib import Path

# ==========================================
# 📜 POWERSHELL CURL CHEAT SHEET
# ==========================================
#
# 1. Create Session:
#    curl.exe -X POST "http://127.0.0.1:5005/session/new" -H "Content-Type: application/json" -d '{\"input_dir\": \"E:/04-Dev Visal/PDF-Toolkit-with-FastAPI-main/Pdf\", \"output_dir\": \"E:/04-Dev Visal/PDF-Toolkit-with-FastAPI-main/workspace\"}'
#
# 2. List Files:
#    curl.exe "http://127.0.0.1:5005/session/<SESSION_ID>/files"
#
# 3. OCR:
#    curl.exe -X POST "http://127.0.0.1:5005/session/<SESSION_ID>/ocr?filename=scan.pdf&output=full"
#
# 4. Markdown:
#    curl.exe -X POST "http://127.0.0.1:5005/session/<SESSION_ID>/to-markdown?filename=doc.pdf&output=full"
#
# 5. Check Status (Time):
#    curl.exe "http://127.0.0.1:5005/session/<SESSION_ID>/status"
#
# 6. Stop Session:
#    curl.exe -X DELETE "http://127.0.0.1:5005/session/<SESSION_ID>"
#
# ==========================================

# ==========================================
# 1. SETUP: Define your local directories
# ==========================================
# Change these to your actual folders!
INPUT_DIR = "E:/04-Dev Visal/PDF-Toolkit-with-FastAPI-main/Pdf"
OUTPUT_DIR = "E:/04-Dev Visal/PDF-Toolkit-with-FastAPI-main/workspace"

# Create the toolkit with custom paths
# If you don't provide input_dir/output_dir, it defaults to ./workspace/input and ./workspace/output
kit = PDFToolkit(
    input_dir=INPUT_DIR,
    output_dir=OUTPUT_DIR
)

print(f"Toolkit ready!")
print(f"Reading from: {kit.paths['input']}")
print(f"Saving to:   {kit.paths['output']}")

# ==========================================
# 2. OCR (Optical Character Recognition)
# ==========================================
# Extract text from images/scanned PDFs

# Example A: Process "scan.pdf" -> Single text file
# Output: {OUTPUT_DIR}/ocr/scan.rapidocr.txt
# full_txt, path = kit.ocr_pdf("scan.pdf", output="full")

# Example B: Process "scan.pdf" -> One text file per page
# Output: {OUTPUT_DIR}/ocr/scan_p0001.rapidocr.txt, ...
# pages_txt, paths = kit.ocr_pdf("scan.pdf", output="pages")


# ==========================================
# 3. PDF to Markdown (Docling)
# ==========================================
# Convert PDF layout/tables to Markdown

# Example A: "report.pdf" -> Single Markdown file
# Output: {OUTPUT_DIR}/markdown/report.md
# full_md, path = kit.pdf_to_markdown("report.pdf", output="full")

# Example B: "report.pdf" -> One Markdown file per page
# Output: {OUTPUT_DIR}/markdown/report_p0001.md, ...
# pages_md, paths = kit.pdf_to_markdown("report.pdf", output="pages")

# Example C: Force OCR (good for scanned docs needing layout preservation)
# md_ocr, paths = kit.pdf_to_markdown("scan.pdf", force_ocr=True, output="pages")


# ==========================================
# 4. Split Pages
# ==========================================

# Example A: Split ALL pages into separate PDFs
# Output: {OUTPUT_DIR}/splits/doc_p0001.pdf, doc_p0002.pdf...
# kit.split_pages("doc.pdf")

# Example B: Extract range (1-5) into ONE combined PDF
# Output: {OUTPUT_DIR}/splits/doc_pages_0001-0005.pdf
# kit.split_pages("doc.pdf", page_range="1-5", combined=True)

# Example C: Extract specific pages (1, 3, 5) into separate PDFs
# kit.split_pages("doc.pdf", pages=[1, 3, 5])

# Example D: Extract specific pages (1, 3, 5) into ONE combined PDF
# kit.split_pages("doc.pdf", pages=[1, 3, 5], combined=True)


# ==========================================
# 5. Merge PDFs
# ==========================================

# Merge "part1.pdf" and "part2.pdf" into "final.pdf"
# Output: {OUTPUT_DIR}/merged/final.pdf
# kit.merge_pdfs(["part1.pdf", "part2.pdf"], out_name="final.pdf")
