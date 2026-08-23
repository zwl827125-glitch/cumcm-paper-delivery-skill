"""Reproduce advanced simulation, distribution, and sensitivity figures.

The figures use deterministic synthetic data so that every gallery render is
repeatable.  They mirror the visual grammar of the supplied reference figures
without treating the screenshots themselves as plot assets.
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from matplotlib.patches import Rectangle
from scipy.stats import gaussian_kde, norm, truncnorm

from plot_common import PALETTE, panel_label, save_figure, style_axis


def _distance_to_rectangle(
    x: np.ndarray,
    y: np.ndarray,
    *,
    half_length: float = 40.0,
    half_width: float = 10.0,
) -> np.ndarray:
    """Euclidean distance from points to an axis-aligned rectangle."""

    dx = np.maximum(np.abs(x) - half_length, 0.0)
    dy = np.maximum(np.abs(y) - half_width, 0.0)
    return np.hypot(dx, dy)


def _hit_mask(
    x: np.ndarray,
    y: np.ndarray,
    *,
    half_length: float = 40.0,
    half_width: float = 10.0,
    blast_radius: float = 20.0,
) -> np.ndarray:
    """Return whether each point falls in the rectangle dilated by R."""

    return (
        _distance_to_rectangle(
            x, y, half_length=half_length, half_width=half_width
        )
        <= blast_radius
    )


def _kde_grid(
    x: np.ndarray,
    y: np.ndarray,
    *,
    xlim: tuple[float, float],
    ylim: tuple[float, float],
    points: int = 150,
    max_samples: int = 5_000,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Evaluate a Gaussian KDE on a regular grid with bounded work."""

    if x.size > max_samples:
        take = np.linspace(0, x.size - 1, max_samples, dtype=int)
        x_fit = x[take]
        y_fit = y[take]
    else:
        x_fit, y_fit = x, y

    gx = np.linspace(*xlim, points)
    gy = np.linspace(*ylim, points)
    xx, yy = np.meshgrid(gx, gy)
    kde = gaussian_kde(np.vstack([x_fit, y_fit]))
    zz = kde(np.vstack([xx.ravel(), yy.ravel()])).reshape(xx.shape)

    assert xx.shape == yy.shape == zz.shape == (points, points), "KDE shape mismatch"
    assert np.all(np.isfinite(zz)) and np.all(zz >= 0), "Invalid KDE density"
    return xx, yy, zz


def _draw_target_and_roi(
    ax,
    *,
    half_length: float = 40.0,
    half_width: float = 10.0,
    blast_radius: float = 20.0,
    show_roi: bool = True,
    zorder_base: float = 5,
    fill_alpha: float = 0.42,
) -> None:
    """Draw the submarine footprint and its rounded hit region."""

    ax.add_patch(
        Rectangle(
            (-half_length, -half_width),
            2 * half_length,
            2 * half_width,
            facecolor=PALETTE["cyan"],
            edgecolor=PALETTE["blue"],
            linewidth=1.0,
            alpha=fill_alpha,
            zorder=zorder_base,
        )
    )
    if show_roi:
        gx = np.linspace(-90, 90, 240)
        gy = np.linspace(-60, 60, 180)
        xx, yy = np.meshgrid(gx, gy)
        distance = _distance_to_rectangle(
            xx, yy, half_length=half_length, half_width=half_width
        )
        ax.contour(
            xx,
            yy,
            distance,
            levels=[blast_radius],
            colors=[PALETTE["blue"]],
            linewidths=1.25,
            linestyles="--",
            zorder=zorder_base + 1,
        )


def make_monte_carlo_kde() -> None:
    """KDE of all samples plus hit/miss classification around a target ROI."""

    rng = np.random.default_rng(2026082201)
    n = 10_000
    samples = rng.multivariate_normal(
        mean=[0.0, 0.0],
        cov=[[120.0**2, -0.06 * 120.0 * 105.0], [-0.06 * 120.0 * 105.0, 105.0**2]],
        size=n,
    )
    x, y = samples.T
    hit = _hit_mask(x, y)
    recomputed = _distance_to_rectangle(x, y) <= 20.0
    assert np.array_equal(hit, recomputed), "Hit classification is inconsistent"
    assert 0.04 < hit.mean() < 0.16, "Synthetic hit rate left its intended range"

    xx, yy, zz = _kde_grid(x, y, xlim=(-400, 400), ylim=(-400, 400), points=155)

    fig, axes = plt.subplots(1, 2, figsize=(8.0, 3.45), constrained_layout=True)
    fig.suptitle("Monte Carlo simulation: position density and hit pattern", y=1.04)

    ax = axes[0]
    levels = np.linspace(0.0, float(zz.max()), 10)
    ax.contourf(xx, yy, zz, levels=levels, cmap="Blues", extend="max")
    ax.scatter(0, 0, marker="x", s=54, linewidths=1.7, color=PALETTE["red"], label="Expected centre", zorder=8)
    _draw_target_and_roi(ax, show_roi=False)
    ax.set(xlim=(-400, 400), ylim=(-400, 400), xlabel="Drop X (m)", ylabel="Drop Y (m)", title="All Monte Carlo samples: Gaussian KDE")
    ax.set_aspect("equal", adjustable="box")
    ax.legend(loc="upper right")
    style_axis(ax, grid=True)
    panel_label(ax, "a")

    ax = axes[1]
    miss = ~hit
    ax.scatter(x[miss], y[miss], s=4.2, color=PALETTE["mid"], alpha=0.18, linewidths=0, rasterized=True, label=f"Miss ({miss.sum():,})")
    ax.scatter(x[hit], y[hit], s=6.0, color=PALETTE["red"], alpha=0.72, linewidths=0, rasterized=True, label=f"Hit ({hit.sum():,})")
    _draw_target_and_roi(ax)
    ax.set(xlim=(-160, 160), ylim=(-90, 90), xlabel="Drop X (m)", ylabel="Drop Y (m)", title="Hit/miss samples near the target")
    ax.set_aspect("equal", adjustable="box")
    ax.legend(loc="upper right", markerscale=1.6)
    style_axis(ax, grid=True)
    panel_label(ax, "b")

    save_figure(fig, "math-repro-monte-carlo-kde")


def make_truncated_distribution_and_optimization() -> None:
    """Truncated normal density and a one-parameter response optimum."""

    lower, mu, sigma = 120.0, 150.0, 35.0
    feasible_low, feasible_high = 137.5, 162.5
    z = np.linspace(100.0, 280.0, 1_200)
    a = (lower - mu) / sigma
    truncated_pdf = truncnorm.pdf(z, a=a, b=np.inf, loc=mu, scale=sigma)
    truncated_pdf = np.where(z >= lower, truncated_pdf, 0.0)
    ordinary_pdf = norm.pdf(z, loc=mu, scale=sigma)

    assert np.all(truncated_pdf[z < lower] == 0.0), "Truncated PDF leaks below its support"
    assert np.all(truncated_pdf[z >= lower] >= 0.0), "Truncated PDF became negative"
    area = np.trapezoid(truncated_pdf, z)
    assert 0.995 < area < 1.005, f"Truncated PDF normalization failed: {area:.5f}"

    d = np.linspace(80.0, 320.0, 1_600)
    response = 3.25 / (1.0 + np.exp(-(d - 108.0) / 12.0)) + 3.10 * np.exp(-0.5 * ((d - 157.0) / 39.0) ** 2)
    optimum_index = int(np.argmax(response))
    d_opt, p_opt = float(d[optimum_index]), float(response[optimum_index])
    assert feasible_low <= d_opt <= feasible_high, "Constructed optimum left the feasible depth band"
    assert response[0] < p_opt and response[-1] < p_opt, "Response optimum is not interior"

    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.25), constrained_layout=True)
    fig.suptitle("Truncated depth distribution and one-parameter optimization", y=1.04)

    ax = axes[0]
    ax.plot(z, ordinary_pdf, linestyle="--", color=PALETTE["mid"], linewidth=1.25, label="Untruncated normal")
    ax.fill_between(z, 0, truncated_pdf, where=z >= lower, color=PALETTE["blue"], alpha=0.24, linewidth=0)
    ax.plot(z, truncated_pdf, color=PALETTE["blue"], linewidth=1.8, label="Truncated normal")
    ax.axvspan(feasible_low, feasible_high, color=PALETTE["green"], alpha=0.17, label="Feasible interval")
    ax.axvline(lower, color=PALETTE["red"], linestyle=":", linewidth=1.25, label=f"Lower bound = {lower:.0f} m")
    ax.axvline(mu, color=PALETTE["cyan"], linestyle="--", linewidth=1.25, label=f"Nominal depth = {mu:.0f} m")
    ax.axvline(feasible_high, color=PALETTE["red"], linewidth=1.25, alpha=0.85, label=f"Candidate = {feasible_high:.1f} m")
    ax.set(
        xlim=(100, 280),
        xlabel="Submarine centre depth Z (m)",
        ylabel="Probability density",
        title="Depth distribution: truncated normal",
    )
    ax.set_ylim(bottom=0)
    ax.legend(loc="upper right", ncol=2, columnspacing=0.9, handlelength=1.8)
    style_axis(ax, grid=False)
    panel_label(ax, "a")

    ax = axes[1]
    ax.plot(d, response, color=PALETTE["blue"], linewidth=1.9, label="Hit probability response")
    ax.axvspan(feasible_low, feasible_high, color=PALETTE["green"], alpha=0.15, label="Feasible depth band")
    ax.axhline(8.4, color=PALETTE["mid"], linestyle="--", linewidth=1.0, label="Reference upper level")
    ax.scatter(d_opt, p_opt, s=44, color=PALETTE["red"], edgecolor="white", linewidth=0.8, zorder=5, label=f"Optimum: {d_opt:.1f} m, {p_opt:.2f}%")
    ax.set(xlim=(80, 320), ylim=(0, 8.8), xlabel="Detonation depth d (m)", ylabel="Hit probability (%)", title="Response versus detonation depth")
    ax.legend(loc="lower right")
    style_axis(ax, grid=True)
    panel_label(ax, "b")

    save_figure(fig, "math-repro-truncated-optimization")


def make_tornado() -> None:
    """Tornado chart using low/high parameter outcomes around one baseline."""

    labels = [
        "Initial depth $h_0$\n(80–250 m)",
        "Depth error $\\sigma_z$\n(5–120 m)",
        "Submarine length\n(20–300 m)",
        "Kill radius $R$\n(5–80 m)",
        "Horizontal error $\\sigma_{xy}$\n(40–300 m)",
    ]
    baseline = 8.5
    low_outcome = np.array([6.0, 9.2, 0.0, 2.7, 40.2])
    high_outcome = np.array([5.1, 5.0, 15.0, 30.8, 2.1])
    assert low_outcome.shape == high_outcome.shape == (len(labels),)

    y = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(7.1, 3.45), constrained_layout=True)
    for offset, values, color, legend_label in [
        (-0.16, low_outcome, PALETTE["blue2"], "Low parameter value"),
        (0.16, high_outcome, PALETTE["coral"], "High parameter value"),
    ]:
        left = np.minimum(values, baseline)
        width = np.abs(values - baseline)
        bars = ax.barh(y + offset, width, left=left, height=0.27, color=color, alpha=0.9, label=legend_label)
        for bar, value in zip(bars, values, strict=True):
            align = "left" if value >= baseline else "right"
            shift = 0.35 if value >= baseline else -0.35
            ax.text(value + shift, bar.get_y() + bar.get_height() / 2, f"{value:.1f}%", va="center", ha=align, fontsize=6.8, color=PALETTE["mid"])

    ax.scatter(np.full_like(y, baseline, dtype=float), y, s=38, marker="D", color=PALETTE["ink"], edgecolor="white", linewidth=0.6, zorder=5, label=f"Baseline ({baseline:.1f}%)")
    ax.axvline(baseline, color=PALETTE["mid"], linestyle=":", linewidth=1.0)
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set(xlim=(-5, 72), xlabel="Hit probability (%)", title="Tornado diagram: parameter sensitivity")
    ax.set_xticks(np.arange(0, 71, 10))
    ax.legend(loc="lower right")
    style_axis(ax, grid=True)
    save_figure(fig, "math-repro-tornado")


def _bounded_beta_samples(
    rng: np.random.Generator,
    low: float,
    high: float,
    n: int,
    a: float,
    b: float,
) -> np.ndarray:
    return low + (high - low) * rng.beta(a, b, size=n)


def make_distance_violin_ecdf() -> None:
    """Grouped violin/box/strip distributions and their empirical CDFs."""

    rng = np.random.default_rng(2026082202)
    bounds = [(0.0, 20.0), (20.0, 40.0), (40.0, 80.0), (80.0, 120.0)]
    shapes = [(2.0, 2.7), (2.4, 2.1), (2.2, 2.4), (2.6, 2.0)]
    groups = [
        _bounded_beta_samples(rng, low, high, 220, a, b)
        for (low, high), (a, b) in zip(bounds, shapes, strict=True)
    ]
    labels = ["0–20", "20–40", "40–80", "80–120"]
    colors = [PALETTE["blue2"], PALETTE["coral"], PALETTE["green"], PALETTE["orange"]]

    for values, (low, high) in zip(groups, bounds, strict=True):
        assert np.all((values >= low) & (values <= high)), "Distance sample left its zone"

    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.45), constrained_layout=True)
    fig.suptitle("Horizontal distance distribution analysis", y=1.04)

    ax = axes[0]
    positions = np.arange(1, len(groups) + 1)
    violin = ax.violinplot(groups, positions=positions, widths=0.78, showmeans=False, showmedians=False, showextrema=False)
    for body, color in zip(violin["bodies"], colors, strict=True):
        body.set_facecolor(color)
        body.set_edgecolor(color)
        body.set_alpha(0.50)
    boxes = ax.boxplot(groups, positions=positions, widths=0.30, patch_artist=True, showfliers=False, medianprops={"color": PALETTE["red"], "linewidth": 1.2}, whiskerprops={"color": PALETTE["ink"], "linewidth": 0.8}, capprops={"color": PALETTE["ink"], "linewidth": 0.8})
    for box in boxes["boxes"]:
        box.set(facecolor="white", edgecolor=PALETTE["ink"], linewidth=0.8, alpha=0.85)
    for pos, values, color in zip(positions, groups, colors, strict=True):
        jitter = rng.normal(0, 0.055, values.size)
        ax.scatter(pos + jitter, values, s=5.5, color=color, alpha=0.24, linewidths=0, rasterized=True)
    ax.axhline(20, color=PALETTE["red"], linestyle="--", linewidth=1.0, label="Hit radius R = 20 m")
    ax.set_xticks(positions, labels)
    ax.set(xlabel="Distance zone (m)", ylabel="Horizontal distance (m)", ylim=(0, 128), title="Violin + box + sample strip")
    ax.legend(loc="upper left")
    style_axis(ax, grid=True)
    panel_label(ax, "a")

    ax = axes[1]
    for values, label, color in zip(groups, labels, colors, strict=True):
        ordered = np.sort(values)
        ecdf = np.arange(1, ordered.size + 1, dtype=float) / ordered.size
        assert np.all(np.diff(ordered) >= 0), "ECDF x-values are not sorted"
        assert np.all(np.diff(ecdf) >= 0) and np.isclose(ecdf[-1], 1.0), "ECDF is not monotone or does not end at 1"
        ax.step(ordered, ecdf, where="post", color=color, linewidth=1.55, label=f"{label} m")
    ax.axvline(20, color=PALETTE["red"], linestyle="--", linewidth=1.0, label="R = 20 m")
    ax.set(xlim=(0, 125), ylim=(0, 1.02), xlabel="Horizontal distance (m)", ylabel="Cumulative probability", title="Empirical CDF by zone")
    ax.legend(loc="lower right")
    style_axis(ax, grid=True)
    panel_label(ax, "b")

    save_figure(fig, "math-repro-distance-ecdf")


def make_correlation_importance() -> None:
    """Lower-triangle correlation heatmap and importance ranking."""

    labels = ["$\\sigma_{xy}$", "$R_{kill}$", "Sub length", "Sub width", "$\\sigma_z$", "$h_0$", "$l_{min}$"]
    corr = np.eye(7)
    lower_values = {
        (1, 0): 0.62,
        (2, 0): 0.45,
        (2, 1): 0.58,
        (3, 0): 0.28,
        (3, 1): 0.38,
        (3, 2): 0.42,
        (4, 0): 0.35,
        (4, 1): 0.30,
        (4, 2): 0.25,
        (4, 3): 0.20,
        (5, 0): 0.15,
        (5, 1): 0.20,
        (5, 2): 0.30,
        (5, 3): 0.25,
        (5, 4): 0.55,
        (6, 0): 0.08,
        (6, 1): 0.12,
        (6, 2): 0.18,
        (6, 3): 0.15,
        (6, 4): 0.48,
        (6, 5): 0.60,
    }
    for (i, j), value in lower_values.items():
        corr[i, j] = value
        corr[j, i] = value
    assert np.allclose(corr, corr.T), "Correlation matrix is not symmetric"
    assert np.allclose(np.diag(corr), 1.0), "Correlation diagonal is not one"

    importance = np.array([0.92, 0.78, 0.62, 0.48, 0.71, 0.55, 0.46])
    bar_colors = [PALETTE["red"], PALETTE["red"], PALETTE["orange"], PALETTE["blue2"], PALETTE["red"], PALETTE["orange"], PALETTE["blue2"]]

    fig, axes = plt.subplots(1, 2, figsize=(8.0, 3.45), constrained_layout=True)
    fig.suptitle("Sensitivity analysis: parameter correlation and importance", y=1.04)

    ax = axes[0]
    mask = np.triu(np.ones_like(corr, dtype=bool), k=1)
    shown = np.ma.array(corr, mask=mask)
    cmap = plt.get_cmap("YlOrRd").copy()
    cmap.set_bad("white")
    image = ax.imshow(shown, vmin=0, vmax=1, cmap=cmap)
    for i in range(corr.shape[0]):
        for j in range(i + 1):
            text_color = "white" if corr[i, j] > 0.64 else PALETTE["ink"]
            ax.text(j, i, f"{corr[i, j]:.2f}", ha="center", va="center", fontsize=6.3, color=text_color)
    ax.set_xticks(range(len(labels)), labels, rotation=90)
    ax.set_yticks(range(len(labels)), labels)
    ax.set_title("Lower-triangle sensitivity correlation")
    for spine in ax.spines.values():
        spine.set_visible(False)
    cbar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Correlation")
    panel_label(ax, "a")

    ax = axes[1]
    ypos = np.arange(len(labels))
    bars = ax.barh(ypos, importance, color=bar_colors, height=0.58)
    ax.axvline(0.5, color=PALETTE["mid"], linestyle=":", linewidth=1.0)
    for bar, score in zip(bars, importance, strict=True):
        ax.text(score + 0.018, bar.get_y() + bar.get_height() / 2, f"{score:.2f}", va="center", fontsize=7, color=PALETTE["mid"])
    ax.set_yticks(ypos, labels)
    ax.set(xlim=(0, 1.06), xlabel="Normalized sensitivity score", title="Parameter importance ranking")
    style_axis(ax, grid=False)
    panel_label(ax, "b")

    save_figure(fig, "math-repro-correlation-importance")


def make_hexbin_kde_overlay() -> None:
    """Monte Carlo hexbin density and KDE contours with hit overlay."""

    rng = np.random.default_rng(2026082203)
    n = 50_000
    samples = rng.multivariate_normal(
        mean=[0.0, 0.0],
        cov=[[155.0**2, 0.10 * 155.0 * 145.0], [0.10 * 155.0 * 145.0, 145.0**2]],
        size=n,
    )
    x, y = samples.T
    hit = _hit_mask(x, y)
    assert np.array_equal(hit, _distance_to_rectangle(x, y) <= 20.0), "Hit overlay disagrees with ROI rule"

    xx, yy, zz = _kde_grid(x, y, xlim=(-520, 520), ylim=(-520, 520), points=145, max_samples=4_500)

    fig, axes = plt.subplots(1, 2, figsize=(8.0, 3.55), constrained_layout=True)
    fig.suptitle("Monte Carlo sample distribution analysis", y=1.04)

    ax = axes[0]
    hb = ax.hexbin(x, y, gridsize=50, extent=(-520, 520, -520, 520), mincnt=1, cmap="YlOrRd", norm=LogNorm(), linewidths=0, rasterized=True)
    ax.scatter(0, 0, marker="x", s=58, linewidths=1.8, color=PALETTE["blue"], zorder=5)
    cbar = fig.colorbar(hb, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Samples per hexagon (log scale)")
    ax.set(xlim=(-520, 520), ylim=(-520, 520), xlabel="X (m)", ylabel="Y (m)", title="Monte Carlo density (hexbin)")
    ax.set_aspect("equal", adjustable="box")
    style_axis(ax, grid=True)
    panel_label(ax, "a")

    ax = axes[1]
    levels = np.linspace(0, float(zz.max()), 9)
    ax.contourf(xx, yy, zz, levels=levels, cmap="Blues", alpha=0.88)
    ax.contour(xx, yy, zz, levels=levels[2:], colors="white", linewidths=0.45, alpha=0.5)
    ax.scatter(
        x[hit],
        y[hit],
        s=5.0,
        color=PALETTE["red"],
        alpha=0.50,
        linewidths=0,
        rasterized=True,
        zorder=7,
        label=f"Hit samples (n={hit.sum():,})",
    )
    _draw_target_and_roi(ax, zorder_base=8, fill_alpha=0.12)
    ax.set(xlim=(-520, 520), ylim=(-520, 520), xlabel="X (m)", ylabel="Y (m)", title="Gaussian KDE contours + hit overlay")
    ax.set_aspect("equal", adjustable="box")
    ax.legend(loc="upper right")
    style_axis(ax, grid=True)
    panel_label(ax, "b")

    save_figure(fig, "math-repro-hexbin-kde")


def main() -> None:
    make_monte_carlo_kde()
    make_truncated_distribution_and_optimization()
    make_tornado()
    make_distance_violin_ecdf()
    make_correlation_importance()
    make_hexbin_kde_overlay()
    print("Generated six reproducible simulation/sensitivity templates (PNG + SVG).")


if __name__ == "__main__":
    main()
