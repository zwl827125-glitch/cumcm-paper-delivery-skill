# Runnable templates

The optional Python templates regenerate 16 formal gallery figures using deterministic demonstration data.

```powershell
python -m pip install -r requirements.txt
python reproduce_all.py
```

Outputs are written to `../assets/previews/modeling-templates/` as 300 dpi PNG and editable-text SVG. Set `SKILL_PLOT_OUTPUT_DIR` to run a clean QA export elsewhere.

Files:

- `reproduce_3d_probability.py`: 3D parametric curve, probability surface/contour, and gradient field.
- `reproduce_simulation_sensitivity.py`: Monte Carlo/KDE, truncated distribution, tornado sensitivity, ECDF, correlation, and hexbin.
- `reproduce_diagnostics_optimization.py`: convergence, bootstrap, regression diagnostics, radar, and optimization landscape.
- `plot_common.py`: shared style and export helpers.
- `reproduce_all.py`: all templates in one command.

Only the parametric curve is formula-exact to its visible reference. Other templates are visual reconstructions using fixed synthetic data; they are not hidden-data reproductions.
