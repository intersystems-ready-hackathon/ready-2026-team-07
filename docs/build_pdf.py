"""Build a single PDF from docs/ARCHITECTURE.md.

Each ```mermaid block is rendered to SVG via the minlag/mermaid-cli Docker
image (no network dependency on kroki.io). The SVGs are then inlined in an
HTML template and rendered to PDF with WeasyPrint.

Run from inside WSL Ubuntu, with Docker accessible:
    python3 docs/build_pdf.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import markdown
from weasyprint import HTML, CSS

ROOT = Path(__file__).parent
SRC = ROOT / "ARCHITECTURE.md"
OUT_PDF = ROOT / "ARCHITECTURE.pdf"
DIAG_DIR = ROOT / "_diagrams"
DIAG_DIR.mkdir(exist_ok=True)

MERMAID_BLOCK = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)
MMDC_IMAGE = "minlag/mermaid-cli"

# Translate the host-side docs path to the path mermaid-cli sees inside the
# container. We mount ROOT at /data, so files written to ROOT appear as /data/<name>.
def render_mermaid(idx: int, source: str) -> Path:
    out = DIAG_DIR / f"diagram_{idx:02d}.svg"
    src_mmd = DIAG_DIR / f"diagram_{idx:02d}.mmd"
    src_mmd.write_text(source, encoding="utf-8")
    print(f"  rendering diagram {idx} ({len(source)} chars) ...", end=" ", flush=True)

    # mermaid-cli inside Docker. Run as current uid:gid so SVG ownership is right.
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{ROOT}:/data",
        "-u", "1000:1000",
        MMDC_IMAGE,
        "-i", f"/data/_diagrams/{src_mmd.name}",
        "-o", f"/data/_diagrams/{out.name}",
        "-b", "transparent",
        "-w", "1600",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print("FAILED")
        print("stdout:", result.stdout)
        print("stderr:", result.stderr)
        sys.exit(1)
    print(f"-> {out.name} ({out.stat().st_size} bytes)")
    return out


def replace_blocks(md_text: str) -> str:
    counter = {"i": 0}

    def repl(m: re.Match) -> str:
        counter["i"] += 1
        idx = counter["i"]
        svg_path = render_mermaid(idx, m.group(1))
        return (
            f'<figure class="diagram">'
            f'<img src="_diagrams/{svg_path.name}" alt="diagram {idx}"/>'
            f'</figure>'
        )

    return MERMAID_BLOCK.sub(repl, md_text)


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>SignBridge Architecture</title>
</head>
<body>
<div class="cover">
  <p class="kicker">Team 07 · InterSystems READY 2026</p>
  <h1>SignBridge</h1>
  <p class="subtitle">Pre-Visit Triage for Deaf Patients on IRIS-for-Health AI Hub</p>
  <p class="byline">Architecture diagrams</p>
</div>
{body}
</body>
</html>
"""

CSS_TEXT = """
@page {
  size: A4;
  margin: 18mm 16mm 18mm 16mm;
  @bottom-center { content: "SignBridge — Architecture · " counter(page) " / " counter(pages); font-family: 'Inter','Helvetica',sans-serif; font-size: 9pt; color: #64748B; }
}
@page :first { @bottom-center { content: ""; } }

html { font-family: 'Inter','Helvetica',sans-serif; font-size: 10.5pt; color: #1E293B; line-height: 1.5; }
body { margin: 0; }

.cover {
  page-break-after: always;
  height: 80vh;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: flex-start;
  padding-left: 6mm;
  border-left: 6px solid #3B82F6;
}
.cover .kicker { color: #64748B; text-transform: uppercase; letter-spacing: 0.2em; font-size: 9pt; margin: 0 0 4mm 0; }
.cover h1 { font-size: 48pt; font-weight: 800; color: #0F172A; margin: 0; letter-spacing: -0.02em; }
.cover .subtitle { font-size: 16pt; color: #334155; margin: 4mm 0 12mm 0; max-width: 140mm; }
.cover .byline { font-size: 10pt; color: #64748B; }

h1 { font-size: 22pt; font-weight: 700; color: #0F172A; margin: 14mm 0 4mm 0; padding-bottom: 2mm; border-bottom: 2px solid #E2E8F0; page-break-after: avoid; }
h2 { font-size: 15pt; font-weight: 700; color: #1E40AF; margin: 10mm 0 3mm 0; page-break-after: avoid; }
h3 { font-size: 12pt; font-weight: 600; color: #1E293B; margin: 6mm 0 2mm 0; page-break-after: avoid; }

p { margin: 0 0 3mm 0; }
ul, ol { margin: 0 0 4mm 6mm; padding-left: 0; }
li { margin: 0 0 1mm 0; }
strong { color: #0F172A; }
em { color: #475569; }

code { font-family: 'JetBrains Mono','Menlo','Consolas',monospace; font-size: 9.5pt; background: #F1F5F9; padding: 1px 4px; border-radius: 3px; color: #0F172A; }
pre { background: #0F172A; color: #E2E8F0; padding: 4mm; border-radius: 4px; font-family: 'JetBrains Mono','Menlo',monospace; font-size: 8.5pt; line-height: 1.5; overflow-wrap: anywhere; }
pre code { background: transparent; color: inherit; padding: 0; }

table { width: 100%; border-collapse: collapse; margin: 3mm 0; font-size: 9.5pt; page-break-inside: avoid; }
th { background: #F1F5F9; color: #0F172A; padding: 2mm 3mm; text-align: left; border-bottom: 2px solid #CBD5E1; font-weight: 600; }
td { padding: 2mm 3mm; border-bottom: 1px solid #E2E8F0; vertical-align: top; }

figure.diagram { margin: 4mm 0 6mm 0; padding: 4mm; background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 4px; text-align: center; page-break-inside: avoid; }
figure.diagram img { max-width: 100%; max-height: 220mm; }

hr { border: none; border-top: 1px solid #E2E8F0; margin: 8mm 0; }

blockquote { border-left: 3px solid #3B82F6; padding: 1mm 4mm; margin: 3mm 0; color: #475569; background: #F8FAFC; }
"""


def main() -> None:
    md_text = SRC.read_text(encoding="utf-8")
    print(f"Reading {SRC} ({len(md_text)} chars)")
    print("Rendering Mermaid diagrams via Docker mermaid-cli ...")

    # Wipe stale SVGs to force regeneration on every run.
    for f in DIAG_DIR.glob("diagram_*.svg"):
        f.unlink()

    md_with_imgs = replace_blocks(md_text)
    body_html = markdown.markdown(
        md_with_imgs,
        extensions=["tables", "fenced_code", "attr_list", "sane_lists"],
    )
    html_full = HTML_TEMPLATE.format(body=body_html)

    print(f"Writing {OUT_PDF} ...")
    HTML(string=html_full, base_url=str(ROOT)).write_pdf(
        str(OUT_PDF),
        stylesheets=[CSS(string=CSS_TEXT)],
    )
    size_kb = OUT_PDF.stat().st_size / 1024
    print(f"Done: {OUT_PDF} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
