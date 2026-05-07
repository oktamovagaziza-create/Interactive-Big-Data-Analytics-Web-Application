from __future__ import annotations

import json
from html import escape
from pathlib import Path

import pandas as pd

from .analyzer import analyze_dataframe


def build_html_report(dataset_path: Path, output_path: Path) -> None:
    df = pd.read_csv(dataset_path)
    analysis = analyze_dataframe(df, filename=dataset_path.name)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    charts = "\n".join(
        f"""
        <section class="chart-card">
          <h2>{escape(chart["title"])}</h2>
          <p>{escape(chart["description"])}</p>
          <div id="{escape(chart["id"])}" class="plot"></div>
          <script>
            Plotly.newPlot({json.dumps(chart["id"])}, {json.dumps(chart["figure"]["data"])}, {json.dumps(chart["figure"]["layout"])}, {{responsive: true, displaylogo: false}});
          </script>
        </section>
        """
        for chart in analysis["visualizations"]
    )

    insights = "\n".join(f"<li>{escape(item)}</li>" for item in analysis["insights"])
    correlations = "\n".join(
        f"<li><strong>{escape(' and '.join(item['columns']))}</strong>: r = {item['correlation']}</li>"
        for item in analysis["statistics"]["top_correlations"]
    )
    metrics = analysis["summary"]

    output_path.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>InsightForge Sample Report</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    body {{ margin: 0; font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #152033; background: #f7fafc; }}
    main {{ max-width: 1160px; margin: 0 auto; padding: 40px 24px; }}
    header {{ margin-bottom: 28px; }}
    h1 {{ font-size: 48px; line-height: 1; margin: 0 0 12px; letter-spacing: 0; }}
    h2 {{ margin: 0 0 8px; }}
    p, li {{ color: #667085; line-height: 1.55; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin: 24px 0; }}
    .metric, .panel, .chart-card {{ background: white; border: 1px solid #d9e2ec; border-radius: 8px; box-shadow: 0 16px 48px rgba(31,44,71,.1); }}
    .metric {{ padding: 18px; }}
    .metric strong {{ display: block; font-size: 30px; color: #0f8b8d; }}
    .panel {{ padding: 24px; margin: 20px 0; }}
    .charts {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
    .chart-card {{ padding: 18px; }}
    .plot {{ min-height: 430px; }}
    @media (max-width: 900px) {{ .grid, .charts {{ grid-template-columns: 1fr; }} h1 {{ font-size: 34px; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Car Sales Automated Analysis</h1>
      <p>Generated from {escape(dataset_path.name)} using the InsightForge analytics pipeline.</p>
    </header>
    <section class="grid">
      <div class="metric"><strong>{metrics["cleaned_shape"][0]:,}</strong><span>Rows</span></div>
      <div class="metric"><strong>{metrics["cleaned_shape"][1]:,}</strong><span>Columns</span></div>
      <div class="metric"><strong>{len(analysis["visualizations"])}</strong><span>Charts</span></div>
      <div class="metric"><strong>{len(analysis["insights"])}</strong><span>Insights</span></div>
    </section>
    <section class="panel">
      <h2>Executive Insights</h2>
      <ul>{insights}</ul>
      <p><strong>Conclusion:</strong> {escape(analysis["conclusions"])}</p>
    </section>
    <section class="panel">
      <h2>Top Correlations</h2>
      <ul>{correlations}</ul>
    </section>
    <section class="charts">{charts}</section>
  </main>
</body>
</html>
""",
        encoding="utf-8",
    )


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    build_html_report(root / "samples" / "car_sales.csv", root / "reports" / "sample_report.html")
