"""Reproduce advanced diagnostic and optimization figures with synthetic data.

The templates mirror the visual grammar of the supplied reference figures while
remaining fully reproducible.  Every random draw uses a fixed seed, every curve
is generated from an explicit formula, and each figure is exported as a 300 dpi
PNG plus an SVG with editable text.
"""

from __future__ import annotations

import math

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Ellipse
from scipy import optimize, stats

from plot_common import PALETTE, panel_label, save_figure, style_axis


SEED = 20260822


def _as_percent(values: np.ndarray) -> np.ndarray:
    """Return a float array used for probability values expressed in percent."""
    return np.asarray(values, dtype=float)


def plot_convergence() -> list[str]:
    """Numerical probability convergence and relative-error decay."""
    # Grid spacing and resolution are linked through a 960 m computational span.
    spacing = np.array([48, 32, 24, 16, 12, 8, 6, 4, 3], dtype=float)
    resolution = np.rint(960 / spacing + 1).astype(int)
    order = np.argsort(resolution)
    resolution = resolution[order]
    spacing = spacing[order]

    limit = _as_percent([8.45, 5.55, 28.10])
    scaled_h = spacing / spacing.max()
    problem_1 = limit[0] + 1.25 * scaled_h**0.90
    problem_2 = limit[1] + 0.55 * scaled_h**0.96
    problem_3 = limit[2] + 10.40 * scaled_h**1.05

    # Numerical convergence contract: discretization error must decrease as the
    # grid gets finer (resolution increases / spacing decreases).
    for curve, target in zip((problem_1, problem_2, problem_3), limit, strict=True):
        absolute_error = np.abs(curve - target)
        assert np.all(np.diff(absolute_error) < 0), "grid refinement did not reduce error"

    finest_1 = problem_1[-1]
    finest_2 = problem_2[-1]
    rel_1 = np.abs(problem_1 - finest_1) / finest_1 * 100
    rel_2 = np.abs(problem_2 - finest_2) / finest_2 * 100
    # Read left-to-right in panel b (small to large spacing): error increases.
    spacing_asc = spacing[::-1]
    rel_1_asc = rel_1[::-1]
    rel_2_asc = rel_2[::-1]
    assert np.all(np.diff(rel_1_asc) > 0)
    assert np.all(np.diff(rel_2_asc) > 0)

    fig, axes = plt.subplots(1, 2, figsize=(8.7, 3.45), constrained_layout=True)
    ax = axes[0]
    ax.semilogx(
        resolution,
        problem_1,
        "o-",
        color=PALETTE["blue"],
        linewidth=1.7,
        markersize=4.0,
        label="Problem 1",
    )
    ax.semilogx(
        resolution,
        problem_2,
        "s--",
        color=PALETTE["orange"],
        linewidth=1.6,
        markersize=3.8,
        label="Problem 2",
    )
    ax.semilogx(
        resolution,
        problem_3,
        "^-." ,
        color=PALETTE["red"],
        linewidth=1.6,
        markersize=4.2,
        label="Problem 3 (scaled)",
    )
    ax.set_title("Probability convergence with grid refinement")
    ax.set_xlabel("Grid resolution, $N \\times N$")
    ax.set_ylabel("Hit probability (%)")
    ax.legend(loc="upper right")
    style_axis(ax, grid=True)
    panel_label(ax, "a")

    ax = axes[1]
    ax.plot(
        spacing_asc,
        rel_1_asc,
        "o-",
        color=PALETTE["blue"],
        linewidth=1.7,
        markersize=4.0,
        label="Problem 1",
    )
    ax.plot(
        spacing_asc,
        rel_2_asc,
        "s--",
        color=PALETTE["orange"],
        linewidth=1.6,
        markersize=3.8,
        label="Problem 2",
    )
    ax.axhline(0.5, color=PALETTE["mid"], linestyle=":", linewidth=1.1, label="0.5% target")
    ax.set_title("Relative error convergence")
    ax.set_xlabel("Grid spacing (m)")
    ax.set_ylabel("Relative error vs finest grid (%)")
    ax.set_xlim(0, 50)
    ax.set_ylim(bottom=-0.35)
    ax.legend(loc="upper left")
    style_axis(ax, grid=True)
    panel_label(ax, "b")

    fig.suptitle("Numerical integration convergence analysis", fontsize=12, y=1.04)
    return [str(path) for path in save_figure(fig, "math-repro-convergence")]


def plot_bootstrap() -> list[str]:
    """Bootstrap box-and-strip distributions with numerical reference lines."""
    rng = np.random.default_rng(SEED + 11)
    reference = _as_percent([8.46, 5.65, 28.30])
    spreads = np.array([0.28, 0.20, 0.95])
    samples = [rng.normal(mu, sd, 50) for mu, sd in zip(reference, spreads, strict=True)]

    for values, target, tolerance in zip(samples, reference, (0.18, 0.13, 0.60), strict=True):
        assert abs(np.mean(values) - target) < tolerance, "bootstrap centre drifted unexpectedly"
        low, high = np.percentile(values, [2.5, 97.5])
        assert low <= target <= high, "reference value is outside the bootstrap interval"

    fig, ax = plt.subplots(figsize=(7.8, 3.8), constrained_layout=True)
    bp = ax.boxplot(
        samples,
        widths=0.34,
        patch_artist=True,
        showfliers=False,
        medianprops={"color": PALETTE["ink"], "linewidth": 1.4},
        whiskerprops={"color": PALETTE["ink"], "linewidth": 1.0},
        capprops={"color": PALETTE["ink"], "linewidth": 1.0},
        boxprops={"edgecolor": PALETTE["ink"], "linewidth": 0.9},
        tick_labels=[
            "Problem 1\n(no depth error)",
            "Problem 2\n(depth error)",
            "Problem 3\n(9-charge array)",
        ],
    )
    box_colors = [PALETTE["blue2"], PALETTE["orange"], PALETTE["coral"]]
    for box, color in zip(bp["boxes"], box_colors, strict=True):
        box.set_facecolor(color)
        box.set_alpha(0.42)

    for i, (values, color) in enumerate(zip(samples, box_colors, strict=True), start=1):
        jitter = rng.uniform(-0.10, 0.10, values.size)
        ax.scatter(
            np.full_like(values, i, dtype=float) + jitter,
            values,
            s=14,
            facecolor=color,
            edgecolor="white",
            linewidth=0.35,
            alpha=0.72,
            zorder=3,
        )

    line_styles = ["--", "--", "--"]
    for target, color, line_style, label in zip(
        reference,
        box_colors,
        line_styles,
        ("P1 numerical: 8.46%", "P2 numerical: 5.65%", "P3 numerical: 28.30%"),
        strict=True,
    ):
        ax.axhline(target, color=color, linestyle=line_style, linewidth=1.25, alpha=0.85, label=label)

    ax.set_title("Bootstrap distribution of hit-probability estimates")
    ax.set_ylabel("Hit probability (%)")
    ax.set_ylim(4.1, 31.3)
    ax.legend(loc="upper left", ncols=3, fontsize=6.6, handlelength=2.2, columnspacing=1.1)
    style_axis(ax, grid=True)
    return [str(path) for path in save_figure(fig, "math-repro-bootstrap")]


def _sigma_model(x: np.ndarray, amplitude: float, tau: float, offset: float) -> np.ndarray:
    return amplitude * np.exp(-x / tau) + offset


def _sigma_jacobian(x: np.ndarray, amplitude: float, tau: float, offset: float) -> np.ndarray:
    del offset
    exponential = np.exp(-x / tau)
    return np.column_stack(
        [exponential, amplitude * exponential * x / tau**2, np.ones_like(x)]
    )


def _radius_model(x: np.ndarray, baseline: float, gain: float, tau: float) -> np.ndarray:
    shifted = np.maximum(x - 5.0, 0.0)
    return baseline + gain * (1.0 - np.exp(-shifted / tau))


def _radius_jacobian(x: np.ndarray, baseline: float, gain: float, tau: float) -> np.ndarray:
    shifted = np.maximum(x - 5.0, 0.0)
    exponential = np.exp(-shifted / tau)
    return np.column_stack(
        [np.ones_like(x), 1.0 - exponential, -gain * exponential * shifted / tau**2]
    )


def _length_model(x: np.ndarray, baseline: float, gain: float, exponent: float) -> np.ndarray:
    """Monotone power-law response used for submarine-length sensitivity."""
    scaled = np.asarray(x, dtype=float) / 300.0
    return baseline + gain * scaled**exponent


def _length_jacobian(x: np.ndarray, baseline: float, gain: float, exponent: float) -> np.ndarray:
    del baseline
    scaled = np.asarray(x, dtype=float) / 300.0
    power = scaled**exponent
    return np.column_stack([np.ones_like(x), power, gain * power * np.log(scaled)])


def _mean_confidence_band(
    x: np.ndarray,
    parameters: np.ndarray,
    covariance: np.ndarray,
    jacobian,
) -> np.ndarray:
    design = jacobian(x, *parameters)
    variance = np.einsum("ij,jk,ik->i", design, covariance, design)
    return 1.96 * np.sqrt(np.clip(variance, 0.0, None))


def _fit_regression_data() -> dict[str, np.ndarray]:
    """Generate and fit the two nonlinear sensitivity relationships."""
    rng = np.random.default_rng(SEED + 23)

    sigma_x = np.linspace(40.0, 300.0, 180)
    sigma_truth = _sigma_model(sigma_x, 38.0, 95.0, -1.2)
    sigma_y = sigma_truth + rng.normal(0.0, 0.72, sigma_x.size)
    sigma_parameters, sigma_covariance = optimize.curve_fit(
        _sigma_model,
        sigma_x,
        sigma_y,
        p0=(30.0, 100.0, 0.0),
        bounds=([10.0, 35.0, -5.0], [55.0, 220.0, 5.0]),
        maxfev=20_000,
    )
    sigma_grid = np.linspace(sigma_x.min(), sigma_x.max(), 400)
    sigma_fit = _sigma_model(sigma_grid, *sigma_parameters)
    sigma_ci = _mean_confidence_band(
        sigma_grid,
        sigma_parameters,
        sigma_covariance,
        _sigma_jacobian,
    )

    radius_x = np.linspace(5.0, 80.0, 165)
    radius_truth = _radius_model(radius_x, 7.2, 29.0, 24.0)
    radius_y = radius_truth + rng.normal(0.0, 0.64, radius_x.size)
    radius_parameters, radius_covariance = optimize.curve_fit(
        _radius_model,
        radius_x,
        radius_y,
        p0=(7.0, 28.0, 25.0),
        bounds=([0.0, 10.0, 5.0], [15.0, 45.0, 80.0]),
        maxfev=20_000,
    )
    radius_grid = np.linspace(radius_x.min(), radius_x.max(), 400)
    radius_fit = _radius_model(radius_grid, *radius_parameters)
    radius_ci = _mean_confidence_band(
        radius_grid,
        radius_parameters,
        radius_covariance,
        _radius_jacobian,
    )

    assert np.all(sigma_fit - sigma_ci <= sigma_fit)
    assert np.all(sigma_fit <= sigma_fit + sigma_ci)
    assert np.all(radius_fit - radius_ci <= radius_fit)
    assert np.all(radius_fit <= radius_fit + radius_ci)
    assert np.all(sigma_ci >= 0) and np.all(radius_ci >= 0)

    return {
        "sigma_x": sigma_x,
        "sigma_y": sigma_y,
        "sigma_grid": sigma_grid,
        "sigma_fit": sigma_fit,
        "sigma_ci": sigma_ci,
        "sigma_parameters": sigma_parameters,
        "radius_x": radius_x,
        "radius_y": radius_y,
        "radius_grid": radius_grid,
        "radius_fit": radius_fit,
        "radius_ci": radius_ci,
        "radius_parameters": radius_parameters,
    }


def plot_regression_fit(data: dict[str, np.ndarray]) -> list[str]:
    """Two nonlinear sensitivity fits with 95% confidence bands."""
    fig, axes = plt.subplots(1, 2, figsize=(8.7, 3.45), constrained_layout=True)

    ax = axes[0]
    ax.scatter(
        data["sigma_x"],
        data["sigma_y"],
        s=11,
        color=PALETTE["blue2"],
        edgecolor="white",
        linewidth=0.25,
        alpha=0.65,
        label="Synthetic samples",
    )
    lower = data["sigma_fit"] - data["sigma_ci"]
    upper = data["sigma_fit"] + data["sigma_ci"]
    ax.fill_between(
        data["sigma_grid"], lower, upper, color=PALETTE["coral"], alpha=0.22, label="95% CI"
    )
    ax.plot(data["sigma_grid"], data["sigma_fit"], color=PALETTE["red"], linewidth=2.0, label="Nonlinear fit")
    ax.axvline(120.0, color=PALETTE["mid"], linestyle="--", linewidth=1.0, label="Nominal value")
    ax.set_title(r"$P$ vs. horizontal uncertainty $\sigma_{xy}$")
    ax.set_xlabel(r"$\sigma_{xy}$ (m)")
    ax.set_ylabel("Hit probability (%)")
    ax.legend(loc="upper right")
    style_axis(ax, grid=True)
    panel_label(ax, "a")

    ax = axes[1]
    ax.scatter(
        data["radius_x"],
        data["radius_y"],
        s=11,
        color=PALETTE["coral"],
        edgecolor="white",
        linewidth=0.25,
        alpha=0.65,
        label="Synthetic samples",
    )
    lower = data["radius_fit"] - data["radius_ci"]
    upper = data["radius_fit"] + data["radius_ci"]
    ax.fill_between(
        data["radius_grid"], lower, upper, color=PALETTE["blue2"], alpha=0.20, label="95% CI"
    )
    ax.plot(data["radius_grid"], data["radius_fit"], color=PALETTE["blue"], linewidth=2.0, label="Nonlinear fit")
    ax.axvline(20.0, color=PALETTE["mid"], linestyle="--", linewidth=1.0, label="Nominal value")
    ax.set_title(r"$P$ vs. effective radius $R$")
    ax.set_xlabel("Effective radius, $R$ (m)")
    ax.set_ylabel("Hit probability (%)")
    ax.legend(loc="lower right")
    style_axis(ax, grid=True)
    panel_label(ax, "b")

    fig.suptitle("Sensitivity analysis: nonlinear regression", fontsize=12, y=1.04)
    return [str(path) for path in save_figure(fig, "math-repro-regression-fit")]


def plot_regression_length_density(data: dict[str, np.ndarray]) -> list[str]:
    """Length sensitivity fit and density-coloured sigma-versus-P relationship."""
    rng = np.random.default_rng(SEED + 37)
    length_x = np.linspace(20.0, 300.0, 180)
    length_truth = _length_model(length_x, 3.55, 13.00, 1.16)
    length_y = length_truth + rng.normal(0.0, 0.52, length_x.size)
    length_parameters, length_covariance = optimize.curve_fit(
        _length_model,
        length_x,
        length_y,
        p0=(3.5, 13.0, 1.1),
        bounds=([0.0, 5.0, 0.35], [8.0, 25.0, 2.5]),
        maxfev=20_000,
    )
    length_grid = np.linspace(length_x.min(), length_x.max(), 400)
    length_fit = _length_model(length_grid, *length_parameters)
    length_ci = _mean_confidence_band(
        length_grid,
        length_parameters,
        length_covariance,
        _length_jacobian,
    )
    lower = length_fit - length_ci
    upper = length_fit + length_ci
    assert np.all(lower <= length_fit) and np.all(length_fit <= upper)
    assert np.all(np.diff(length_fit) > 0), "length-response fit must be monotone increasing"
    length_residuals = length_y - _length_model(length_x, *length_parameters)
    assert float(np.sqrt(np.mean(length_residuals**2))) < 0.65

    sigma_x = data["sigma_x"]
    sigma_y = data["sigma_y"]
    standardized = np.vstack(
        [
            (sigma_x - np.mean(sigma_x)) / np.std(sigma_x),
            (sigma_y - np.mean(sigma_y)) / np.std(sigma_y),
        ]
    )
    density = stats.gaussian_kde(standardized, bw_method="scott")(standardized)
    draw_order = np.argsort(density)
    assert density.size == sigma_x.size == sigma_y.size
    assert np.all(np.isfinite(density)) and np.all(density > 0.0)
    assert float(np.max(density) / np.min(density)) > 2.0

    fig, axes = plt.subplots(1, 2, figsize=(8.7, 3.45), constrained_layout=True)

    ax = axes[0]
    ax.scatter(
        length_x,
        length_y,
        s=12,
        color=PALETTE["green"],
        edgecolor="white",
        linewidth=0.25,
        alpha=0.66,
        label="Synthetic samples",
    )
    ax.fill_between(
        length_grid,
        lower,
        upper,
        color=PALETTE["green"],
        alpha=0.18,
        label="95% CI",
    )
    ax.plot(length_grid, length_fit, color=PALETTE["red"], linewidth=2.0, label="Nonlinear fit")
    ax.axvline(100.0, color=PALETTE["mid"], linestyle="--", linewidth=1.0, label="Nominal value")
    ax.set_title(r"$P$ vs. submarine length $L$")
    ax.set_xlabel("Submarine length, $L$ (m)")
    ax.set_ylabel("Hit probability (%)")
    ax.legend(loc="upper left")
    style_axis(ax, grid=True)
    panel_label(ax, "a")

    ax = axes[1]
    density_scatter = ax.scatter(
        sigma_x[draw_order],
        sigma_y[draw_order],
        c=density[draw_order],
        cmap="YlOrRd",
        s=16,
        edgecolor="none",
        alpha=0.84,
    )
    ax.plot(
        data["sigma_grid"],
        data["sigma_fit"],
        color=PALETTE["ink"],
        linewidth=1.25,
        alpha=0.75,
        label="Nonlinear fit",
    )
    colorbar = fig.colorbar(density_scatter, ax=ax, pad=0.025, shrink=0.88)
    colorbar.set_label("Local point density")
    colorbar.set_ticks([])
    colorbar.outline.set_linewidth(0.7)
    ax.set_title(r"Joint density: $\sigma_{xy}$ vs. $P$")
    ax.set_xlabel(r"$\sigma_{xy}$ (m)")
    ax.set_ylabel("Hit probability (%)")
    ax.legend(loc="upper right")
    style_axis(ax, grid=True)
    panel_label(ax, "b")

    fig.suptitle("Sensitivity relationships", fontsize=12, y=1.04)
    return [str(path) for path in save_figure(fig, "math-repro-regression-length-density")]


def plot_residual_qq(data: dict[str, np.ndarray]) -> list[str]:
    """Residual-versus-fitted and normal Q-Q diagnostics."""
    sigma_fitted_at_samples = _sigma_model(data["sigma_x"], *data["sigma_parameters"])
    residuals = data["sigma_y"] - sigma_fitted_at_samples
    assert residuals.size == data["sigma_x"].size
    assert np.all(np.isfinite(residuals))
    assert abs(float(np.mean(residuals))) < 0.12

    fig, axes = plt.subplots(1, 2, figsize=(8.7, 3.45), constrained_layout=True)

    ax = axes[0]
    ax.scatter(
        sigma_fitted_at_samples,
        residuals,
        s=13,
        color=PALETTE["blue2"],
        edgecolor="white",
        linewidth=0.25,
        alpha=0.72,
    )
    ax.axhline(0.0, color=PALETTE["red"], linewidth=1.4)
    ax.axhline(np.std(residuals), color=PALETTE["mid"], linestyle=":", linewidth=0.9)
    ax.axhline(-np.std(residuals), color=PALETTE["mid"], linestyle=":", linewidth=0.9)
    ax.set_title("Residuals vs. fitted values")
    ax.set_xlabel("Fitted hit probability (%)")
    ax.set_ylabel("Residual")
    style_axis(ax, grid=True)
    panel_label(ax, "a")

    theoretical, ordered = stats.probplot(residuals, dist="norm", fit=False)
    slope, intercept = np.polyfit(theoretical, ordered, 1)
    line_x = np.array([np.min(theoretical), np.max(theoretical)])
    ax = axes[1]
    ax.scatter(
        theoretical,
        ordered,
        s=16,
        color=PALETTE["blue"],
        edgecolor="white",
        linewidth=0.25,
        alpha=0.78,
    )
    ax.plot(line_x, slope * line_x + intercept, color=PALETTE["red"], linewidth=1.6)
    ax.set_title("Normal Q–Q plot")
    ax.set_xlabel("Theoretical quantiles")
    ax.set_ylabel("Ordered residuals")
    style_axis(ax, grid=True)
    panel_label(ax, "b")

    fig.suptitle("Regression diagnostics", fontsize=12, y=1.04)
    return [str(path) for path in save_figure(fig, "math-repro-residual-qq")]


def plot_model_radar() -> list[str]:
    """Multi-model comparison across six direction-normalized metrics."""
    labels = [
        "Hit\nprobability",
        "Coverage",
        "Simplicity",
        "Compute\nefficiency",
        "Scalability",
        "Noise\nrobustness",
    ]
    scores = {
        "Problem 1: 2D": np.array([0.42, 0.30, 0.86, 0.90, 0.44, 0.78]),
        "Problem 2: depth": np.array([0.61, 0.55, 0.72, 0.69, 0.64, 0.66]),
        "Problem 3: array": np.array([0.94, 0.92, 0.34, 0.38, 0.82, 0.40]),
    }
    assert all(np.all((values >= 0.0) & (values <= 1.0)) for values in scores.values())

    count = len(labels)
    angles = np.linspace(0, 2 * np.pi, count, endpoint=False)
    closed_angles = np.r_[angles, angles[0]]

    fig = plt.figure(figsize=(6.2, 5.0), constrained_layout=True)
    ax = fig.add_subplot(111, polar=True)
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_xticks(angles)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylim(0, 1.0)
    ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels(["0.2", "0.4", "0.6", "0.8", "1.0"], fontsize=6.8, color=PALETTE["mid"])
    ax.set_rlabel_position(12)
    ax.grid(color=PALETTE["light"], linewidth=0.8)
    ax.spines["polar"].set_color(PALETTE["mid"])
    ax.spines["polar"].set_linewidth(0.8)

    styles = [
        (PALETTE["blue"], "-", "o"),
        (PALETTE["orange"], "--", "s"),
        (PALETTE["red"], "-.", "^") ,
    ]
    for (name, values), (color, linestyle, marker) in zip(scores.items(), styles, strict=True):
        closed_values = np.r_[values, values[0]]
        ax.plot(
            closed_angles,
            closed_values,
            color=color,
            linestyle=linestyle,
            marker=marker,
            markersize=4.0,
            linewidth=1.6,
            label=name,
        )
        ax.fill(closed_angles, closed_values, color=color, alpha=0.08)

    ax.set_title(
        "Multi-dimensional model comparison\n(direction-normalized score; higher is better)",
        fontsize=11,
        pad=22,
    )
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.10), ncols=3, fontsize=7.2)
    return [str(path) for path in save_figure(fig, "math-repro-model-radar")]


def _optimization_probability(spacing: np.ndarray, depth: np.ndarray) -> np.ndarray:
    """Smooth super-elliptic objective with a broad rectangular high-value basin."""
    optimum_spacing = 105.4
    optimum_depth = 165.8
    horizontal = np.abs((spacing - optimum_spacing) / 68.0) ** 3.2
    vertical = np.abs((depth - optimum_depth) / 24.0) ** 4.0
    return 5.0 + 27.0 * np.exp(-(horizontal + vertical))


def plot_optimization_landscape() -> list[str]:
    """Filled contour objective with feasibility constraints and its optimum."""
    spacing_values = np.linspace(0.0, 180.0, 361)
    depth_values = np.linspace(130.0, 190.0, 241)
    spacing_grid, depth_grid = np.meshgrid(spacing_values, depth_values)
    probability = _optimization_probability(spacing_grid, depth_grid)

    maximum_index = np.unravel_index(np.argmax(probability), probability.shape)
    grid_optimum = np.array(
        [spacing_grid[maximum_index], depth_grid[maximum_index]], dtype=float
    )
    analytic_optimum = np.array([105.4, 165.8])
    assert np.linalg.norm(grid_optimum - analytic_optimum) < 0.35
    assert math.isclose(float(probability[maximum_index]), 32.0, rel_tol=0.0, abs_tol=0.01)

    feasible_low, feasible_high = 137.5, 162.5
    optimum_probability = float(_optimization_probability(*analytic_optimum))
    assert optimum_probability > float(probability.min())

    fig, ax = plt.subplots(figsize=(7.1, 4.6), constrained_layout=True)
    levels = np.linspace(5.0, 32.0, 12)
    filled = ax.contourf(
        spacing_grid,
        depth_grid,
        probability,
        levels=levels,
        cmap="YlOrRd",
        extend="max",
    )
    contours = ax.contour(
        spacing_grid,
        depth_grid,
        probability,
        levels=levels[1:-1:2],
        colors=PALETTE["mid"],
        linewidths=0.55,
        alpha=0.50,
    )
    ax.clabel(contours, inline=True, fontsize=6.3, fmt="%.0f")

    ax.axhspan(feasible_low, feasible_high, color=PALETTE["green"], alpha=0.075, zorder=2)
    ax.axhline(feasible_low, color=PALETTE["green"], linestyle=":", linewidth=1.2, zorder=4)
    ax.axhline(feasible_high, color=PALETTE["green"], linestyle=":", linewidth=1.2, zorder=4)
    ax.text(
        3.5,
        feasible_low + 0.8,
        "Feasible depth band",
        color=PALETTE["green"],
        fontsize=7.2,
        va="bottom",
        ha="left",
    )

    ax.scatter(
        analytic_optimum[0],
        analytic_optimum[1],
        marker="*",
        s=190,
        facecolor="white",
        edgecolor=PALETTE["cyan"],
        linewidth=1.6,
        zorder=7,
        label=f"Optimum: s={analytic_optimum[0]:.1f} m, d={analytic_optimum[1]:.1f} m",
    )
    ax.add_patch(
        Ellipse(
            xy=analytic_optimum,
            width=20.0,
            height=7.0,
            facecolor="none",
            edgecolor=PALETTE["cyan"],
            linestyle="--",
            linewidth=1.2,
            zorder=6,
        )
    )

    colorbar = fig.colorbar(filled, ax=ax, pad=0.025, shrink=0.96)
    colorbar.set_label("Hit probability (%)")
    colorbar.outline.set_linewidth(0.7)
    ax.set_title(r"Optimization landscape $P(s,d)$")
    ax.set_xlabel("Grid spacing, $s$ (m)")
    ax.set_ylabel("Detonation depth, $d$ (m)")
    ax.set_xlim(0, 180)
    ax.set_ylim(130, 190)
    ax.legend(loc="lower right", fontsize=7.0)
    style_axis(ax, grid=False)
    return [str(path) for path in save_figure(fig, "math-repro-optimization-landscape")]


def main() -> None:
    generated: list[str] = []
    generated.extend(plot_convergence())
    generated.extend(plot_bootstrap())
    regression_data = _fit_regression_data()
    generated.extend(plot_regression_fit(regression_data))
    generated.extend(plot_regression_length_density(regression_data))
    generated.extend(plot_residual_qq(regression_data))
    generated.extend(plot_model_radar())
    generated.extend(plot_optimization_landscape())

    expected_stems = {
        "math-repro-convergence",
        "math-repro-bootstrap",
        "math-repro-regression-fit",
        "math-repro-regression-length-density",
        "math-repro-residual-qq",
        "math-repro-model-radar",
        "math-repro-optimization-landscape",
    }
    generated_stems = {path.rsplit(".", 1)[0].split("\\")[-1].split("/")[-1] for path in generated}
    assert generated_stems == expected_stems
    assert len(generated) == 2 * len(expected_stems)
    print("Generated and validated:")
    for path in generated:
        print(f"  {path}")


if __name__ == "__main__":
    main()
