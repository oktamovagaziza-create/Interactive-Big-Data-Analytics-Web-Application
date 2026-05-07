from __future__ import annotations

import json
import math
from dataclasses import dataclass
from io import BytesIO
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.utils import PlotlyJSONEncoder
from scipy import stats


MAX_ROWS_FOR_CHARTS = 5000


@dataclass
class ColumnProfile:
    numeric: list[str]
    categorical: list[str]
    datetime: list[str]
    text: list[str]


def parse_dataset(filename: str, content: bytes) -> pd.DataFrame:
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix == "csv":
        try:
            return pd.read_csv(BytesIO(content))
        except UnicodeDecodeError:
            return pd.read_csv(BytesIO(content), encoding="latin-1")
    if suffix in {"xlsx", "xls"}:
        return pd.read_excel(BytesIO(content))
    raise ValueError("Unsupported file type. Upload a CSV or Excel file.")


def analyze_dataframe(df: pd.DataFrame, filename: str = "dataset") -> dict[str, Any]:
    if df.empty or df.shape[1] == 0:
        raise ValueError("The uploaded file is empty or has no readable columns.")

    original_shape = list(df.shape)
    df = normalize_columns(df)
    df = drop_empty_rows_and_columns(df)
    df = coerce_datetime_columns(df)
    profile = classify_columns(df)
    cleaned = clean_dataframe(df, profile)
    profile = classify_columns(cleaned)

    charts = build_charts(cleaned, profile)
    correlations = top_correlations(cleaned, profile.numeric)
    outliers = detect_outliers(cleaned, profile.numeric)
    stats_summary = build_statistics(cleaned, profile, correlations, outliers)
    insights = generate_insights(cleaned, profile, correlations, outliers, charts)

    return {
        "filename": filename,
        "preview": dataframe_preview(cleaned),
        "summary": {
            "original_shape": original_shape,
            "cleaned_shape": list(cleaned.shape),
            "rows_removed": max(original_shape[0] - cleaned.shape[0], 0),
            "columns_removed": max(original_shape[1] - cleaned.shape[1], 0),
            "missing_values": missing_values(df),
            "cleaned_missing_values": missing_values(cleaned),
            "data_types": {col: str(dtype) for col, dtype in cleaned.dtypes.items()},
            "column_types": profile.__dict__,
        },
        "statistics": stats_summary,
        "visualizations": charts,
        "insights": insights,
        "conclusions": build_conclusions(insights),
    }


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    seen: dict[str, int] = {}
    columns = []
    for raw in df.columns:
        name = str(raw).strip() or "unnamed"
        name = " ".join(name.replace("_", " ").split()).title()
        seen[name] = seen.get(name, 0) + 1
        columns.append(f"{name} {seen[name]}" if seen[name] > 1 else name)
    df.columns = columns
    return df


def drop_empty_rows_and_columns(df: pd.DataFrame) -> pd.DataFrame:
    return df.dropna(axis=0, how="all").dropna(axis=1, how="all")


def coerce_datetime_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            continue
        if pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_string_dtype(df[col]):
            non_null = df[col].dropna()
            if non_null.empty:
                continue
            sample = non_null.astype(str).head(200)
            looks_date_like = sample.str.contains(r"\d{4}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", regex=True).mean()
            if looks_date_like >= 0.55:
                converted = pd.to_datetime(df[col], errors="coerce")
                if converted.notna().mean() >= 0.65:
                    df[col] = converted
    return df


def classify_columns(df: pd.DataFrame) -> ColumnProfile:
    numeric: list[str] = []
    categorical: list[str] = []
    datetime: list[str] = []
    text: list[str] = []

    for col in df.columns:
        series = df[col]
        if pd.api.types.is_datetime64_any_dtype(series):
            datetime.append(col)
        elif pd.api.types.is_numeric_dtype(series):
            numeric.append(col)
        else:
            unique_ratio = series.nunique(dropna=True) / max(len(series), 1)
            avg_len = series.dropna().astype(str).str.len().mean() if series.notna().any() else 0
            if unique_ratio <= 0.35 or series.nunique(dropna=True) <= 30:
                categorical.append(col)
            elif avg_len > 30:
                text.append(col)
            else:
                categorical.append(col)
    return ColumnProfile(numeric=numeric, categorical=categorical, datetime=datetime, text=text)


def clean_dataframe(df: pd.DataFrame, profile: ColumnProfile) -> pd.DataFrame:
    cleaned = df.copy()
    cleaned = cleaned.drop_duplicates()
    for col in profile.numeric:
        cleaned[col] = pd.to_numeric(cleaned[col], errors="coerce")
        if cleaned[col].isna().any():
            cleaned[col] = cleaned[col].fillna(cleaned[col].median())
    for col in profile.categorical + profile.text:
        if cleaned[col].isna().any():
            mode = cleaned[col].mode(dropna=True)
            fallback = mode.iloc[0] if not mode.empty else "Unknown"
            cleaned[col] = cleaned[col].fillna(fallback)
    for col in profile.datetime:
        if cleaned[col].isna().any():
            cleaned[col] = cleaned[col].fillna(cleaned[col].dropna().median())
    return cleaned


def dataframe_preview(df: pd.DataFrame) -> dict[str, Any]:
    preview = df.head(20).copy()
    for col in preview.select_dtypes(include=["datetime64[ns]", "datetimetz"]).columns:
        preview[col] = preview[col].dt.strftime("%Y-%m-%d")
    return {
        "columns": list(preview.columns),
        "rows": json.loads(preview.replace({np.nan: None}).to_json(orient="records", date_format="iso")),
    }


def missing_values(df: pd.DataFrame) -> dict[str, int]:
    return {col: int(value) for col, value in df.isna().sum().items()}


def figure_json(fig: go.Figure, chart_id: str, title: str, kind: str, description: str) -> dict[str, Any]:
    fig.update_layout(
        template="plotly_white",
        margin=dict(l=48, r=28, t=72, b=48),
        title=dict(text=title, x=0.02, xanchor="left"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return {
        "id": chart_id,
        "title": title,
        "type": kind,
        "description": description,
        "figure": json.loads(json.dumps(fig, cls=PlotlyJSONEncoder)),
    }


def chart_frame(df: pd.DataFrame) -> pd.DataFrame:
    if len(df) <= MAX_ROWS_FOR_CHARTS:
        return df
    return df.sample(MAX_ROWS_FOR_CHARTS, random_state=7)


def build_charts(df: pd.DataFrame, profile: ColumnProfile) -> list[dict[str, Any]]:
    charts: list[dict[str, Any]] = []
    plot_df = chart_frame(df)

    if profile.datetime and profile.numeric:
        date_col = profile.datetime[0]
        numeric_col = best_numeric(profile.numeric, df)
        grouped = (
            df[[date_col, numeric_col]]
            .dropna()
            .set_index(date_col)
            .sort_index()
            .resample("ME")[numeric_col]
            .mean()
            .reset_index()
        )
        if len(grouped) >= 2:
            fig = px.area(grouped, x=date_col, y=numeric_col, markers=True)
            charts.append(figure_json(fig, "trend", f"Trend of {numeric_col} Over Time", "area", "Monthly average trend for the strongest numeric measure."))

    for col in profile.numeric[:3]:
        fig = px.histogram(plot_df, x=col, marginal="box", nbins=30)
        charts.append(figure_json(fig, f"hist-{slug(col)}", f"{col} Distribution", "histogram", "Distribution with box summary for skew and outliers."))

    if profile.categorical:
        cat = best_categorical(profile.categorical, df)
        counts = df[cat].value_counts().head(12).reset_index()
        counts.columns = [cat, "Count"]
        fig = px.bar(counts, x=cat, y="Count", text_auto=True)
        charts.append(figure_json(fig, "category-bars", f"Top {cat} Categories", "bar", "Largest categorical segments by record count."))

        pie_counts = df[cat].value_counts().head(8).reset_index()
        pie_counts.columns = [cat, "Count"]
        fig = px.pie(pie_counts, names=cat, values="Count", hole=0.45)
        charts.append(figure_json(fig, "category-share", f"{cat} Share", "donut", "Share of records across the leading categories."))

    if len(profile.numeric) >= 2:
        x_col, y_col = strongest_numeric_pair(df, profile.numeric)
        fig = px.scatter(plot_df, x=x_col, y=y_col, opacity=0.72)
        regression = regression_line(plot_df, x_col, y_col)
        if regression is not None:
            line_x, line_y = regression
            fig.add_trace(go.Scatter(x=line_x, y=line_y, mode="lines", name="Regression line", line=dict(color="#e11d48", width=3)))
        charts.append(figure_json(fig, "scatter-regression", f"{x_col} vs {y_col}", "scatter", "Relationship between two numeric features with regression fit."))

        corr = df[profile.numeric].corr(numeric_only=True).round(2)
        fig = px.imshow(corr, text_auto=True, aspect="auto", color_continuous_scale="RdBu_r", zmin=-1, zmax=1)
        charts.append(figure_json(fig, "correlation-heatmap", "Numeric Correlation Heatmap", "heatmap", "Pairwise Pearson correlations across numeric columns."))

    if profile.numeric and profile.categorical:
        numeric_col = best_numeric(profile.numeric, df)
        cat = best_categorical(profile.categorical, df)
        top_values = df[cat].value_counts().head(8).index
        filtered = plot_df[plot_df[cat].isin(top_values)]
        if not filtered.empty:
            fig = px.violin(filtered, x=cat, y=numeric_col, box=True, points="outliers")
            charts.append(figure_json(fig, "category-violin", f"{numeric_col} by {cat}", "violin", "Category-level spread, medians, and outliers."))

    return charts


def best_numeric(columns: list[str], df: pd.DataFrame) -> str:
    return max(columns, key=lambda col: float(df[col].std()) if df[col].notna().sum() else 0.0)


def best_categorical(columns: list[str], df: pd.DataFrame) -> str:
    return max(columns, key=lambda col: min(df[col].nunique(dropna=True), 20))


def strongest_numeric_pair(df: pd.DataFrame, columns: list[str]) -> tuple[str, str]:
    corr = df[columns].corr(numeric_only=True).abs()
    best: tuple[str, str, float] = (columns[0], columns[1], -1.0)
    for i, col_a in enumerate(columns):
        for col_b in columns[i + 1 :]:
            value = corr.loc[col_a, col_b]
            if pd.notna(value) and value > best[2]:
                best = (col_a, col_b, float(value))
    return best[0], best[1]


def regression_line(df: pd.DataFrame, x_col: str, y_col: str) -> tuple[list[float], list[float]] | None:
    clean = df[[x_col, y_col]].dropna()
    clean = clean[np.isfinite(clean[x_col]) & np.isfinite(clean[y_col])]
    if len(clean) < 3 or clean[x_col].nunique() < 2:
        return None
    slope, intercept = np.polyfit(clean[x_col], clean[y_col], 1)
    line_x = [float(clean[x_col].min()), float(clean[x_col].max())]
    line_y = [float(slope * x + intercept) for x in line_x]
    return line_x, line_y


def top_correlations(df: pd.DataFrame, columns: list[str]) -> list[dict[str, Any]]:
    if len(columns) < 2:
        return []
    corr = df[columns].corr(numeric_only=True)
    records: list[dict[str, Any]] = []
    for i, col_a in enumerate(columns):
        for col_b in columns[i + 1 :]:
            value = corr.loc[col_a, col_b]
            if pd.notna(value):
                records.append({"columns": [col_a, col_b], "correlation": round(float(value), 3)})
    return sorted(records, key=lambda item: abs(item["correlation"]), reverse=True)[:10]


def detect_outliers(df: pd.DataFrame, columns: list[str]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for col in columns:
        series = df[col].dropna()
        if len(series) < 8 or series.std() == 0:
            continue
        z_scores = np.abs(stats.zscore(series, nan_policy="omit"))
        count = int((z_scores > 3).sum())
        if count:
            results.append({
                "column": col,
                "count": count,
                "share": round(count / len(series), 4),
                "min": round(float(series.min()), 3),
                "max": round(float(series.max()), 3),
            })
    return sorted(results, key=lambda item: item["count"], reverse=True)[:8]


def build_statistics(df: pd.DataFrame, profile: ColumnProfile, correlations: list[dict[str, Any]], outliers: list[dict[str, Any]]) -> dict[str, Any]:
    numeric_stats = {}
    if profile.numeric:
        numeric_stats = json.loads(df[profile.numeric].describe().round(3).replace({np.nan: None}).to_json())
    categorical_stats = {
        col: df[col].value_counts().head(10).to_dict()
        for col in profile.categorical[:6]
    }
    return {
        "numeric_describe": numeric_stats,
        "categorical_top_values": categorical_stats,
        "top_correlations": correlations,
        "outliers": outliers,
    }


def generate_insights(
    df: pd.DataFrame,
    profile: ColumnProfile,
    correlations: list[dict[str, Any]],
    outliers: list[dict[str, Any]],
    charts: list[dict[str, Any]],
) -> list[str]:
    insights: list[str] = []
    rows, cols = df.shape
    insights.append(f"The cleaned dataset contains {rows:,} rows and {cols:,} columns, with {len(profile.numeric)} numeric, {len(profile.categorical)} categorical, and {len(profile.datetime)} datetime fields.")

    if correlations:
        top = correlations[0]
        direction = "positive" if top["correlation"] > 0 else "negative"
        insights.append(f"The strongest numeric relationship is a {direction} correlation between {top['columns'][0]} and {top['columns'][1]} (r = {top['correlation']}).")

    if profile.categorical:
        cat = best_categorical(profile.categorical, df)
        leader = df[cat].value_counts().head(1)
        if not leader.empty:
            share = leader.iloc[0] / len(df)
            insights.append(f"{leader.index[0]} is the leading {cat} segment, representing {share:.1%} of all records.")

    if profile.numeric:
        num = best_numeric(profile.numeric, df)
        skew = df[num].skew()
        if pd.notna(skew) and abs(skew) > 0.8:
            tail = "right" if skew > 0 else "left"
            insights.append(f"{num} is meaningfully {tail}-skewed, so averages should be interpreted alongside medians and quartiles.")

    if profile.datetime and profile.numeric:
        date_col = profile.datetime[0]
        num = best_numeric(profile.numeric, df)
        trend = df[[date_col, num]].dropna().sort_values(date_col)
        if len(trend) > 4:
            first = trend.head(max(1, len(trend) // 5))[num].mean()
            last = trend.tail(max(1, len(trend) // 5))[num].mean()
            if first and not math.isclose(first, 0):
                change = (last - first) / abs(first)
                insights.append(f"{num} changed by {change:.1%} from the earliest period to the latest period in the dataset.")

    if outliers:
        focus = outliers[0]
        insights.append(f"{focus['column']} contains {focus['count']} statistical outliers beyond 3 standard deviations; these records deserve review before operational decisions.")

    if charts:
        insights.append(f"The system generated {len(charts)} interactive visualizations covering distributions, segment mix, relationships, and trend behavior.")

    return insights


def build_conclusions(insights: list[str]) -> str:
    if not insights:
        return "The dataset was processed successfully, but there were not enough fields to generate deeper automated conclusions."
    return " ".join(insights) + " Recommendation: validate the highlighted outliers, prioritize the largest segments, and use the strongest numeric drivers as starting points for deeper business analysis."


def slug(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")
