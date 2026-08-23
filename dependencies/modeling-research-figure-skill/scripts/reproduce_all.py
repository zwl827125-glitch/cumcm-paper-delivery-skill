"""Regenerate every advanced mathematical-modeling gallery template."""

from reproduce_3d_probability import main as reproduce_3d_probability
from reproduce_diagnostics_optimization import main as reproduce_diagnostics_optimization
from reproduce_simulation_sensitivity import main as reproduce_simulation_sensitivity


def main() -> None:
    reproduce_3d_probability()
    reproduce_simulation_sensitivity()
    reproduce_diagnostics_optimization()


if __name__ == "__main__":
    main()
