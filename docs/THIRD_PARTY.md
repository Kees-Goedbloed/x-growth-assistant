# Third-party licenses

The dashboard **runtime** is the Python 3.12 standard library plus these
committed vendor files (inlined into `index.html` at build time; no CDN):

| Component | Path | License |
|---|---|---|
| [Apache ECharts](https://echarts.apache.org/) 5.6.0 | `vendor/echarts/echarts.min.js` | Apache License 2.0 (`vendor/echarts/LICENSE`) |
| [Inter](https://github.com/rsms/inter) latin 400 / 600 / 700 | `vendor/fonts/*.woff2` | SIL Open Font License 1.1 (`vendor/fonts/LICENSE`) |

CI / contributor tools (`requirements-dev.txt`) are optional and not required
to build a dashboard:

| Package | License (upstream) |
|---|---|
| ruff 0.13.2 | MIT |
| pip-audit 2.9.0 | Apache-2.0 |
| pillow 12.3.0 | HPND |

There are no other pip runtime dependencies to audit.
