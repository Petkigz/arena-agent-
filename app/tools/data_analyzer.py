import os
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for headless PNG generation
import matplotlib.pyplot as plt
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.config import settings
from app.utils.logger import app_logger, audit_logger

class DataAnalysisEngine:
    CHARTS_DIR = settings.DATA_DIR / "workspace" / "charts"

    @classmethod
    def ensure_dir(cls):
        cls.CHARTS_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def analyze_dataset(cls, file_path_str: str) -> Dict[str, Any]:
        """
        Reads CSV or Excel dataset with pandas and computes summary statistics, missing values, and correlations.
        """
        p = Path(file_path_str)
        if not p.is_absolute():
            p = settings.BASE_DIR / p

        if not p.exists():
            return {"success": False, "error": f"Dataset file not found: '{p}'"}

        ext = p.suffix.lower()

        try:
            if ext == ".csv":
                df = pd.read_csv(p)
            elif ext in [".xlsx", ".xls"]:
                df = pd.read_excel(p)
            else:
                return {"success": False, "error": f"Unsupported dataset format '{ext}'. Use CSV or Excel files."}

            num_rows, num_cols = df.shape
            columns = list(df.columns)
            summary_stats = df.describe().to_dict()
            missing_counts = df.isnull().sum().to_dict()

            audit_logger.info(f"Analyzed dataset '{p.name}' ({num_rows} rows, {num_cols} cols)")

            return {
                "success": True,
                "file_name": p.name,
                "rows_count": num_rows,
                "columns_count": num_cols,
                "columns": columns,
                "summary_stats": summary_stats,
                "missing_values": missing_counts,
                "data_head_json": df.head(5).to_dict(orient="records")
            }
        except Exception as e:
            app_logger.error(f"Data analysis error on '{p.name}': {e}")
            return {"success": False, "error": f"Data analysis error: {str(e)}"}

    @classmethod
    def generate_chart_visualization(
        cls, 
        file_path_str: str, 
        x_col: str, 
        y_col: str, 
        chart_type: str = "bar",
        chart_title: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generates data visualization PNG charts (bar, line, scatter, histogram) and saves them in data/workspace/charts/.
        """
        cls.ensure_dir()
        p = Path(file_path_str)
        if not p.is_absolute():
            p = settings.BASE_DIR / p

        if not p.exists():
            return {"success": False, "error": f"Dataset file not found: '{p}'"}

        try:
            df = pd.read_csv(p) if p.suffix.lower() == ".csv" else pd.read_excel(p)

            if x_col not in df.columns or y_col not in df.columns:
                return {"success": False, "error": f"Columns '{x_col}' or '{y_col}' not found in dataset. Available: {list(df.columns)}"}

            plt.figure(figsize=(10, 6), facecolor='#0b0f19')
            ax = plt.gca()
            ax.set_facecolor('#111827')
            ax.tick_params(colors='#f9fafb')
            ax.xaxis.label.set_color('#00f2fe')
            ax.yaxis.label.set_color('#00f2fe')
            ax.title.set_color('#f9fafb')

            if chart_type == "line":
                plt.plot(df[x_col], df[y_col], color='#00f2fe', marker='o', linewidth=2)
            elif chart_type == "scatter":
                plt.scatter(df[x_col], df[y_col], color='#3b82f6', alpha=0.7)
            elif chart_type == "histogram":
                plt.hist(df[y_col], bins=15, color='#8b5cf6', edgecolor='#1f2937')
            else: # Default bar
                plt.bar(df[x_col].astype(str), df[y_col], color='#00f2fe')

            title = chart_title or f"{y_col} vs {x_col} ({chart_type.upper()})"
            plt.title(title, fontsize=14, pad=15)
            plt.xlabel(x_col)
            plt.ylabel(y_col)
            plt.grid(True, linestyle='--', alpha=0.2, color='#374151')

            chart_filename = f"chart_{chart_type}_{p.stem}.png"
            chart_file_path = cls.CHARTS_DIR / chart_filename
            plt.savefig(chart_file_path, bbox_inches='tight', dpi=150)
            plt.close()

            audit_logger.info(f"Generated chart visualization '{chart_filename}'")

            return {
                "success": True,
                "chart_filename": chart_filename,
                "chart_file_path": str(chart_file_path),
                "image_url": f"/static/workspace/charts/{chart_filename}",
                "chart_type": chart_type
            }
        except Exception as e:
            app_logger.error(f"Chart generation error: {e}")
            return {"success": False, "error": f"Chart error: {str(e)}"}
