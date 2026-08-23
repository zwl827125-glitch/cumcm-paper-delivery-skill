"""Reproduce the gallery's 3-D and hit-probability reference figures.

The figures use deterministic synthetic data so that the visual grammar can be
reused without presenting the values as experimental evidence.
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import colors

from plot_common import PALETTE, panel_label, save_figure, style_axis


def _set_3d_panes(ax) -> None:
    """Use a faint technical grid without visually overpowering 3-D geometry."""
    pane = (0.97, 0.98, 0.99, 1.0)
    ax.xaxis.set_pane_color(pane)
    ax.yaxis.set_pane_color(pane)
    ax.zaxis.set_pane_color(pane)
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis._axinfo["grid"].update(  # noqa: SLF001 - Matplotlib 3-D styling hook
            {"color": (0.78, 0.82, 0.85, 0.68), "linewidth": 0.65}
        )


def parametric_data() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return the exact arrays shown in the user's Python reference."""
    x = np.linspace(0.0, 10.0, 100)
    y = np.sin(x)
    z = np.cos(x)
    c = np.sin(x) * np.cos(x)

    assert np.array_equal(y, np.sin(x))
    assert np.array_equal(z, np.cos(x))
    assert np.array_equal(c, y * z)
    assert c.min() < -0.49 and c.max() > 0.49
    assert np.max(np.abs(c)) <= 0.5 + 1e-12
    return x, y, z, c


def make_parametric_scatter() -> tuple[str, str]:
    """Colored triangular 3-D parametric scatter, matching the code reference."""
    x, y, z, c = parametric_data()

    fig = plt.figure(figsize=(10.0, 7.0), constrained_layout=True)
    ax = fig.add_subplot(111, projection="3d")
    _set_3d_panes(ax)

    scatter = ax.scatter(
        x,
        y,
        z,
        c=c,
        cmap="cool",
        marker="^",
        s=100,
        alpha=0.60,
        edgecolors="none",
        depthshade=False,
        label="Data points",
        zorder=2,
    )

    ax.set(
        xlabel="X-axis",
        ylabel="Y-axis",
        zlabel="Z-axis",
        xlim=(0.0, 10.0),
        ylim=(-1.1, 1.1),
        zlim=(-1.1, 1.1),
        title="3D Scatter Plot with Custom Markers",
    )
    ax.set_xticks(np.arange(0, 11, 2))
    ax.set_yticks([-1.0, -0.5, 0.0, 0.5, 1.0])
    ax.set_zticks([-1.0, -0.5, 0.0, 0.5, 1.0])
    ax.view_init(elev=24, azim=-61)
    ax.set_box_aspect((1.65, 1.0, 1.0))
    cbar = fig.colorbar(scatter, ax=ax, shrink=0.76, pad=0.085, aspect=24)
    cbar.set_label("Color intensity")

    png, svg = save_figure(fig, "math-repro-3d-parametric")
    return str(png), str(svg)


def probability_field() -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
]:
    """Create a smooth, rectangular hit-probability field and its gradient."""
    x = np.linspace(-200.0, 200.0, 161)
    y = np.linspace(-200.0, 200.0, 161)
    xx, yy = np.meshgrid(x, y)

    # A sixth-order anisotropic super-Gaussian creates the flat rectangular peak
    # and sharp fall-off visible in the source surface and contour map.
    half_width_x = 45.0
    half_width_y = 90.0
    core = np.exp(-((np.abs(xx) / half_width_x) ** 6 + (np.abs(yy) / half_width_y) ** 6))
    probability = 2.0 + 97.98 * core
    probability_fraction = probability / 100.0
    grad_y, grad_x = np.gradient(probability_fraction, y, x)

    center = (len(y) // 2, len(x) // 2)
    assert x[center[1]] == 0.0 and y[center[0]] == 0.0
    assert np.isclose(probability[center], 99.98, atol=1e-12)
    assert np.argmax(probability) == np.ravel_multi_index(center, probability.shape)
    assert probability.min() >= 2.0 and probability.max() <= 99.98 + 1e-12

    # Gradient checks at each side of the high-probability region: every vector
    # must point back toward the optimum at the origin.
    ix_pos = int(np.argmin(np.abs(x - half_width_x)))
    ix_neg = int(np.argmin(np.abs(x + half_width_x)))
    iy_pos = int(np.argmin(np.abs(y - half_width_y)))
    iy_neg = int(np.argmin(np.abs(y + half_width_y)))
    assert grad_x[center[0], ix_pos] < 0.0
    assert grad_x[center[0], ix_neg] > 0.0
    assert grad_y[iy_pos, center[1]] < 0.0
    assert grad_y[iy_neg, center[1]] > 0.0

    active = np.hypot(grad_x, grad_y) > 1e-5
    inward_dot = -(xx * grad_x + yy * grad_y)
    assert np.all(inward_dot[active] >= -1e-12)
    return xx, yy, probability, grad_x, grad_y, probability_fraction


def make_probability_surface_contour() -> tuple[str, str]:
    """Reproduce the paired 3-D surface and 2-D probability contour."""
    xx, yy, probability, _, _, _ = probability_field()
    levels = np.linspace(2.0, 99.98, 12)
    norm = colors.Normalize(vmin=2.0, vmax=99.98)

    fig = plt.figure(figsize=(10.4, 4.4), constrained_layout=True)
    ax_surface = fig.add_subplot(121, projection="3d")
    ax_contour = fig.add_subplot(122)
    _set_3d_panes(ax_surface)

    surface = ax_surface.plot_surface(
        xx,
        yy,
        probability,
        cmap="YlOrRd",
        norm=norm,
        rcount=81,
        ccount=81,
        linewidth=0.0,
        antialiased=True,
        shade=False,
    )
    ax_surface.scatter(
        [0],
        [0],
        [99.98],
        s=31,
        color=PALETTE["blue"],
        depthshade=False,
        label="Optimum (0, 0)",
    )
    ax_surface.set(
        xlabel="Drop X (m)",
        ylabel="Drop Y (m)",
        zlabel="Hit probability (%)",
        xlim=(-200, 200),
        ylim=(-200, 200),
        zlim=(0, 102),
        title="3D probability surface",
    )
    ax_surface.view_init(elev=29, azim=-60)
    ax_surface.set_box_aspect((1.0, 1.0, 0.72))
    ax_surface.legend(loc="upper left", bbox_to_anchor=(0.17, 0.96))
    ax_surface.text2D(
        -0.08,
        1.06,
        "a",
        transform=ax_surface.transAxes,
        fontsize=15,
        fontweight="bold",
        va="top",
        ha="right",
        color=PALETTE["ink"],
    )
    cbar_surface = fig.colorbar(surface, ax=ax_surface, shrink=0.72, pad=0.08, aspect=24)
    cbar_surface.set_label("Hit probability (%)")

    contour = ax_contour.contourf(
        xx,
        yy,
        probability,
        levels=levels,
        cmap="YlOrRd",
        norm=norm,
        extend="both",
    )
    ax_contour.contour(
        xx,
        yy,
        probability,
        levels=[20, 50, 80, 95],
        colors="white",
        linewidths=0.65,
        alpha=0.8,
    )
    ax_contour.scatter(
        [0],
        [0],
        marker="x",
        s=62,
        linewidths=2.0,
        color=PALETTE["blue"],
        label="Optimum (0, 0)",
        zorder=4,
    )
    ax_contour.set(
        xlabel="Drop X (m)",
        ylabel="Drop Y (m)",
        xlim=(-200, 200),
        ylim=(-200, 200),
        title="Contour map of hit probability",
    )
    ax_contour.set_aspect("equal")
    style_axis(ax_contour, grid=False)
    ax_contour.legend(loc="upper right")
    panel_label(ax_contour, "b")
    cbar_contour = fig.colorbar(contour, ax=ax_contour, shrink=0.88, pad=0.035, aspect=24)
    cbar_contour.set_label("Hit probability (%)")

    png, svg = save_figure(fig, "math-repro-probability-surface-contour")
    return str(png), str(svg)


def make_probability_gradient() -> tuple[str, str]:
    """Reproduce a probability gradient field whose arrows lead to the optimum."""
    xx, yy, probability, grad_x, grad_y, _ = probability_field()
    magnitude = np.hypot(grad_x, grad_y)

    fig, ax = plt.subplots(figsize=(6.1, 5.25), constrained_layout=True)
    probability_display = 1.0 + 8.0 * (probability - 2.0) / 97.98
    background = ax.contourf(
        xx,
        yy,
        probability_display,
        levels=np.linspace(1.0, 9.0, 9),
        cmap="YlOrRd",
        alpha=0.20,
    )
    ax.contour(
        xx,
        yy,
        probability_display,
        levels=[2.5, 5.0, 7.5],
        colors=[PALETTE["light"], PALETTE["mid"], PALETTE["ink"]],
        linewidths=[0.7, 0.8, 0.9],
        alpha=0.72,
    )

    stride = 8
    xq = xx[::stride, ::stride]
    yq = yy[::stride, ::stride]
    uq = grad_x[::stride, ::stride]
    vq = grad_y[::stride, ::stride]
    mq = magnitude[::stride, ::stride]
    active_threshold = magnitude.max() * 0.022
    mask = mq < active_threshold
    denom = np.where(mq > 0.0, mq, 1.0)
    uq = np.ma.array(uq / denom, mask=mask)
    vq = np.ma.array(vq / denom, mask=mask)
    cq = np.ma.array(mq, mask=mask)

    quiver = ax.quiver(
        xq,
        yq,
        uq,
        vq,
        cq,
        cmap="Blues",
        norm=colors.Normalize(vmin=0.0, vmax=float(magnitude.max())),
        angles="xy",
        scale_units="xy",
        scale=0.072,
        width=0.006,
        headwidth=3.7,
        headlength=4.8,
        pivot="mid",
        zorder=3,
    )
    ax.scatter(
        [0],
        [0],
        s=45,
        color=PALETTE["red"],
        edgecolor="white",
        linewidth=0.8,
        label="Optimum (0, 0)",
        zorder=5,
    )
    ax.set(
        xlabel="Drop X (m)",
        ylabel="Drop Y (m)",
        xlim=(-200, 200),
        ylim=(-200, 200),
        title="Gradient field of hit probability",
    )
    ax.set_aspect("equal")
    style_axis(ax, grid=True)
    ax.legend(loc="upper right")
    cbar_gradient = fig.colorbar(
        quiver, ax=ax, location="left", pad=0.08, aspect=28, shrink=0.92
    )
    cbar_gradient.set_label("Gradient magnitude (1/m)")
    cbar_probability = fig.colorbar(
        background, ax=ax, location="right", pad=0.025, aspect=28, shrink=0.92
    )
    cbar_probability.set_label("Probability (%)")
    cbar_probability.set_ticks(np.arange(1.0, 10.0, 1.0))

    png, svg = save_figure(fig, "math-repro-probability-gradient")
    return str(png), str(svg)


def main() -> None:
    outputs = [
        make_parametric_scatter(),
        make_probability_surface_contour(),
        make_probability_gradient(),
    ]
    _, _, _, grad_x, grad_y, _ = probability_field()
    print("Generated reproducible 3-D probability templates:")
    for png, svg in outputs:
        print(f"  PNG: {png}")
        print(f"  SVG: {svg}")
    print(
        "Checks: c in [-0.5, 0.5]; peak P(0,0)=99.98%; "
        f"max |gradient|={np.hypot(grad_x, grad_y).max():.5f} m^-1; "
        "all active gradients point inward."
    )


if __name__ == "__main__":
    main()
