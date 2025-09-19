from main import PDFToolkit
kit = PDFToolkit(base_dir="/data/pdf_ws")   # or default "workspace"

kit.ingest(["/path/to/a.pdf", "/path/to/b.pdf"])

===================================================================

# OCR
full_txt, full_txt_path   = kit.ocr_pdf(output="full")    # one combined TXT, with page breakers
pages_txt, page_txt_paths = kit.ocr_pdf(output="pages")   # per-page TXT files

# Markdown (no OCR)
full_md, full_md_path     = kit.pdf_to_markdown(output="full")   # one combined MD
pages_md, page_md_paths   = kit.pdf_to_markdown(output="pages")  # per-page MD files

# Markdown (force OCR inside Docling)
md_pages_ocr, md_paths_ocr = kit.pdf_to_markdown(force_ocr=True, output="pages")

# Split pages
# a) split ALL pages to separate PDFs (default behavior)
outs_all_separate = kit.split_pages()

# b) split a RANGE (1–5) into ONE combined PDF
outs_range_combined = kit.split_pages(page_range="1-5", combined=True)

# c) split specific pages (2, 7, 11, 15) into separate PDFs
outs_specific_separate = kit.split_pages(pages=[2, 7, 11, 15])

# d) split specific pages (2, 7, 11, 15) into ONE combined PDF
outs_specific_combined = kit.split_pages(pages=[2, 7, 11, 15], combined=True)


==================================================================

# OCR & Markdown for a specific file
txt, txt_path          = kit.ocr_pdf("a.pdf", output="full")
mds, md_paths          = kit.pdf_to_markdown("a.pdf", output="pages")
mds_ocr, md_paths_ocr  = kit.pdf_to_markdown("a.pdf", force_ocr=True, output="pages")

# Split pages for a specific file
# a) split ALL pages of a.pdf to separate PDFs
outs_all = kit.split_pages(pdf_path="a.pdf")

# b) split range (1–5) of a.pdf into ONE combined PDF
outs_range = kit.split_pages(pdf_path="a.pdf", page_range="1-5", combined=True)

# c) split specific pages of a.pdf into separate PDFs
outs_specific = kit.split_pages(pdf_path="a.pdf", pages=[2, 7, 11, 15])

# d) split specific pages of a.pdf into ONE combined PDF
outs_specific_combined = kit.split_pages(pdf_path="a.pdf", pages=[2, 7, 11, 15], combined=True)

# Merge (unchanged)
merged = kit.merge_pdfs(["a.pdf", "b.pdf"], out_name="merged.pdf")

