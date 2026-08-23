"""Shared publication-style helpers for the reproducible gallery templates."""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt


SCRIPT_DIR = Path(__file__).resolve().parent
GALLERY_DIR = SCRIPT_DIR.parent
OUTPUT_DIR = Path(
    os.environ.get(
        "SKILL_PLOT_OUTPUT_DIR",
        str(GALLERY_DIR / "assets" / "previews" / "modeling-templates"),
    )
).resolve()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PALETTE = {
    "blue": "#0F4D92",
    "blue2": "#4EA5D9",
    "cyan": "#61D4E8",
    "red": "#C73E32",
    "coral": "#F08A7E",
    "orange": "#F29E4C",
    "gold": "#F6D365",
    "green": "#3BA272",
    "violet": "#8E62B4",
    "magenta": "#D94FD5",
    "ink": "#25313C",
    "mid": "#6D7882",
    "light": "#DDE5EB",
    "wash": "#F5F8FA",
}


def configure_style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Microsoft YaHei", "DejaVu Sans", "sans-serif"],
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "font.size": 8,
            "axes.labelsize": 9,
            "axes.titlesize": 10,
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
            "legend.fontsize": 7.2,
            "axes.spines.right": False,
            "axes.spines.top": False,
            "axes.linewidth": 0.8,
            "legend.frameon": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )


def style_axis(ax, *, grid: bool = False) -> None:
    ax.tick_params(width=0.8, length=3, color=PALETTE["mid"])
    if grid:
        ax.grid(True, color=PALETTE["light"], linewidth=0.7, alpha=0.65)
        ax.set_axisbelow(True)


def panel_label(ax, label: str) -> None:
    ax.text(
        -0.08,
        1.06,
        label,
        transform=ax.transAxes,
        fontsize=15,
        fontweight="bold",
        va="top",
        ha="right",
        color=PALETTE["ink"],
    )


def save_figure(fig, stem: str, *, dpi: int = 300) -> tuple[Path, Path]:
    """Save editable SVG and high-resolution PNG, then close the figure."""
    png = OUTPUT_DIR / f"{stem}.png"
    svg = OUTPUT_DIR / f"{stem}.svg"
    fig.savefig(svg, bbox_inches="tight")
    fig.savefig(png, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    if not png.exists() or png.stat().st_size == 0:
        raise RuntimeError(f"PNG export failed: {png}")
    if not svg.exists() or "<text" not in svg.read_text(encoding="utf-8"):
        raise RuntimeError(f"SVG editable text check failed: {svg}")
    return png, svg


configure_style()
