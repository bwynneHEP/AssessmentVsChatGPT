# html_report.py
from datetime import datetime
from html import escape

def write_html_report(output_path: str, pdf_path: str, model: str, questions: list[str], answers: list[str]):
    """
    Writes a minimal static HTML file with any number of Q/A sections.
    questions and answers are zipped together; if lengths differ, extra items are ignored.
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sections_html = []
    for i, (q, a) in enumerate(zip(questions, answers), start=1):
        q = q or "(no question)"
        a = a or "(no reply)"
        sections_html.append(f"""
      <div class="card">
        <h2>{i}) {escape(q[:160]) + ('…' if len(q) > 160 else '')}</h2>
        <div class="answer"><pre>{escape(a)}</pre></div>
      </div>""")

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>PDF Analysis Report</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial; margin: 24px; line-height: 1.45; }}
    h1, h2 {{ margin: 0 0 8px; }}
    .meta {{ color: #666; font-size: 0.9rem; margin-bottom: 20px; }}
    .card {{ border: 1px solid #e5e7eb; border-radius: 10px; padding: 14px; margin: 12px 0; background: #fff; }}
    pre {{ white-space: pre-wrap; word-wrap: break-word; }}
    .answer {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; }}
  </style>
</head>
<body>
  <h1>PDF Analysis Report</h1>
  <div class="meta">
    Source PDF: {escape(pdf_path)}<br>
    Model: {escape(model)}<br>
    Generated: {escape(ts)}
  </div>
  {''.join(sections_html)}
</body>
</html>"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

