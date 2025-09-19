# pdf_client.py
import requests
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote

class PDFClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")
        self.session_id: Optional[str] = None

    # ---------------- Session ----------------
    def start_session(self) -> str:
        r = requests.post(f"{self.base_url}/session/start")
        r.raise_for_status()
        self.session_id = r.json()["session_id"]
        return self.session_id

    def cleanup_session(self):
        self._assert_session()
        r = requests.delete(f"{self.base_url}/session/{self.session_id}")
        r.raise_for_status()
        return r.json()

    # ---------------- Upload ----------------
    def upload(self, pdf_paths: List[str]):
        self._assert_session()
        files = [("files", (Path(p).name, open(p, "rb"), "application/pdf")) for p in pdf_paths]
        r = requests.post(f"{self.base_url}/session/{self.session_id}/upload", files=files)
        r.raise_for_status()
        return r.json()

    # ---------------- OCR ----------------
    def ocr(self, filename: Optional[str] = None, output: str = "full", preprocess: bool = True):
        self._assert_session()
        params = {"filename": filename, "output": output, "preprocess": preprocess}
        r = requests.post(f"{self.base_url}/session/{self.session_id}/ocr", params=params)
        r.raise_for_status()
        return r.json()

    # ---------------- Markdown ----------------
    def to_markdown(self, filename: Optional[str] = None, force_ocr: bool = False, output: str = "full"):
        self._assert_session()
        params = {"filename": filename, "force_ocr": force_ocr, "output": output}
        r = requests.post(f"{self.base_url}/session/{self.session_id}/to-markdown", params=params)
        r.raise_for_status()
        return r.json()

    # ---------------- Split (QUERY PARAMS) ----------------
    def split_pages(
        self,
        filename: Optional[str] = None,
        pages: Optional[List[int]] = None,
        page_range: Optional[str] = None,
        combined: bool = False,
    ):
        self._assert_session()
        qp = []
        if filename is not None:
            qp.append(("filename", filename))
        if page_range is not None:
            qp.append(("page_range", page_range))
        qp.append(("combined", str(combined).lower()))
        if pages:
            for p in pages:
                qp.append(("pages", str(int(p))))
        r = requests.post(f"{self.base_url}/session/{self.session_id}/split-pages", params=qp)
        r.raise_for_status()
        return r.json()

    # ---------------- Merge (QUERY PARAMS) ----------------
    def merge(self, filenames: List[str], out_name: str = "merged.pdf"):
        self._assert_session()
        qp = [("out_name", out_name)]
        for f in filenames:
            qp.append(("filenames", f))
        r = requests.post(f"{self.base_url}/session/{self.session_id}/merge", params=qp)
        r.raise_for_status()
        return r.json()

    # ---------------- Download ----------------
    def download(self, server_path: str, save_as: str):
        """
        server_path MUST be a path RELATIVE to the session base, e.g.:
          'output/splits/Matrix_Sample_p0001.pdf'
        """
        self._assert_session()
        url = f"{self.base_url}/session/{self.session_id}/download/{quote(server_path)}"
        print("GET:", url)  # <-- debug so you can see it's output/splits/...
        r = requests.get(url, stream=True)
        if r.status_code != 200:
            raise RuntimeError(f"Download failed: {r.status_code} {r.text}")
        with open(save_as, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return save_as

    # ---------------- Helpers ----------------
    def _assert_session(self):
        if not self.session_id:
            raise RuntimeError("No session started. Call start_session() first.")

    @staticmethod
    def to_relative_from_api(raw_path: str, session_id: str) -> str:
        """
        Convert absolute Windows/POSIX path from API to the relative path
        expected by /download/{filename}.
        Example:
          raw: '\\tmp\\pdf_processing\\<sid>\\output\\splits\\Matrix_Sample_p0001.pdf'
          ->  'output/splits/Matrix_Sample_p0001.pdf'
        """
        p = raw_path.replace("\\", "/")
        anchor = f"/{session_id}/"
        idx = p.find(anchor)
        if idx != -1:
            rel = p[idx + len(anchor):]
        else:
            rel = p.lstrip("/")
        return rel


# ---------------- Example: split pages 1, 7, 19 ----------------
if __name__ == "__main__":
    client = PDFClient("http://localhost:8000")

    # 1) Start session
    sid = client.start_session()
    print("Session:", sid)

    # 2) Upload one PDF
    client.upload(["Matrix_Sample.pdf"])

    # 3) Split pages 1,7,19 into SEPARATE PDFs
    split_sep = client.split_pages(pages=[1, 7, 19], combined=False)
    print("Split (separate):", split_sep)

    # Download each of the SEPARATE files using the EXACT paths returned
    for i, raw in enumerate(split_sep["output_files"], start=1):
        rel = client.to_relative_from_api(raw, sid)
        assert rel.startswith("output/"), f"Refusing to download non-output path: {rel}"
        client.download(rel, f"Matrix_Sample_page_{i}.pdf")

    # 4) Split pages 1,7,19 into ONE COMBINED PDF
    split_comb = client.split_pages(pages=[1, 7, 19], combined=True)
    print("Split (combined):", split_comb)

    # Download the combined file (again: use the returned path)
    rel_comb = client.to_relative_from_api(split_comb["output_files"][0], sid)
    assert rel_comb.startswith("output/"), f"Refusing to download non-output path: {rel_comb}"
    client.download(rel_comb, "Matrix_Sample_pages_1_7_19.pdf")

    # 5) (optional) cleanup
    print(client.cleanup_session())
