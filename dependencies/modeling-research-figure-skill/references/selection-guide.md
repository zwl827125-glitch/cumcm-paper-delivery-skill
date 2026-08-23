# Figure selection guide

Use this guide only after the user's conclusion and available data are clear.

## Mathematical-modeling contests

| Evidence goal | Start with |
|---|---|
| Show a two-parameter objective and optimum | `modeling-optimization-landscape` |
| Explain a probability field spatially | `modeling-probability-surface-contour`, then `modeling-probability-gradient` |
| Validate simulation behavior | `modeling-monte-carlo-kde` or `modeling-hexbin-kde` |
| Rank parameter sensitivity | `modeling-tornado-sensitivity` or `modeling-correlation-importance` |
| Demonstrate numerical reliability | `modeling-convergence` and `modeling-bootstrap` |
| Validate a regression model | `modeling-regression-fit`, `modeling-regression-density`, and `modeling-residual-qq` |
| Compare several models across metrics | `modeling-model-radar` |
| Explain geometry, movement, or mechanism | `modeling-example-trajectory-geometry` |
| Explain a periodic or spectral mechanism | `modeling-example-mechanism-trends` or `modeling-example-diagnostic-grid` |

For a contest paper, prefer one conclusion per figure. Split dense four-panel references when the submission format or page width makes them unreadable.

## Research papers

| Evidence goal | Start with |
|---|---|
| Ordinary comparisons or time courses | `research-atlas-bars` or `research-atlas-lines` |
| Sample-level distributions | `research-atlas-distributions` |
| Associations, clusters, or multiple encodings | `research-atlas-scatter` |
| Effect sizes and uncertainty | `research-atlas-forest` |
| Compositional change | `research-atlas-area` |
| Interactions and networks | `research-atlas-network` |
| Multi-channel imaging | `research-atlas-images`, then `research-blueprint-imaging` |
| Mechanism plus material validation | `research-blueprint-material` |
| In-vivo efficacy and safety | `research-blueprint-clinical` |
| Single-cell or systems evidence | `research-blueprint-single-cell` |
| Perturbation, synergy, and validation | `research-blueprint-validation` |

## Composition rules

- Use a single chart when one quantitative comparison proves the claim.
- Use a quantitative grid when several parallel metrics carry equal weight.
- Use a hero panel plus supporting panels when one mechanism, image, or embedding anchors the conclusion.
- Use static references as blueprints. Rebuild the figure with the user's data and statistics rather than tracing values from pixels.
- Recommend at most three starting references unless the user explicitly asks to browse the whole gallery.
