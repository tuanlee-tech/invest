"""Bounded live feasibility probe, not a production ingestion pipeline.

Run with Python 3.12 and pypdf==6.19.0, requests==2.34.2.
Saves evidence locally; never treats extracted text as validated holdings.
"""

import argparse
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import requests
from pypdf import PdfReader


SOURCES = {
    "vesaf-202608": "https://vinacapital.com/wp-content/uploads/2026/09/20260915-VINACAPITAL-VESAF_Monthly-Factsheet_Aug-2026-EN.pdf",
    "vesaf-202607": "https://vinacapital.com/wp-content/uploads/2026/08/20260814-VINACAPITAL-VESAF_Monthly-Factsheet_Jul-2026-EN.pdf",
    "vcbf-bcf-202608": "https://www.vcbf.com/images/2026/b_ng_th_ng_tin_qu_u_t_c_phi_u_h_ng_u_vcbf_-_th_ng_082026.pdf",
    "vcbf-bcf-202607": "https://www.vcbf.com/images/2026/b_ng_th_ng_tin_qu_u_t_c_phi_u_h_ng_u_vcbf_-_th_ng_072026.pdf",
    "veil-202608": "https://cdn.dragoncapital.com/media/2026/09/16111336/VEIL_Factsheet_202608.pdf",
    "veil-202607": "https://cdn.dragoncapital.com/media/2026/08/17053110/VEIL_Factsheet_202607.pdf",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=SOURCES)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = Path(__file__).resolve().parent / "runs" / stamp
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for name, url in SOURCES.items():
        if args.only and name != args.only:
            continue
        row = {"id": name, "url": url, "retrieved_at": datetime.now(timezone.utc).isoformat()}
        try:
            response = requests.get(url, timeout=40)
            row.update(status=response.status_code, final_url=response.url)
            response.raise_for_status()
            raw = response.content
            if not raw.startswith(b"%PDF-"):
                raise ValueError("Response is not a PDF")
            row.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            (output / f"{name}.pdf").write_bytes(raw)
            reader = PdfReader(io.BytesIO(raw))
            text = "\n".join(f"--- PAGE {i} ---\n{p.extract_text() or ''}" for i, p in enumerate(reader.pages, 1))
            (output / f"{name}.txt").write_text(text, encoding="utf-8")
            row.update(pages=len(reader.pages), text_chars=len(text), text_extractable=len(text) > 500)
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
        results.append(row)
        print(json.dumps(row, ensure_ascii=True))
    (output / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Evidence directory: {output}")


if __name__ == "__main__":
    main()
