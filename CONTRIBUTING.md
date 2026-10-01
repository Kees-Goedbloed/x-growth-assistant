# Contributing

## Setup

```bash
git clone <this-repo>
cd x-growth-assistant
./scripts/setup.sh        # or: make setup
# demo fixtures, public HTML → ./index.html, then the unit tests
```

Python 3.12+ is enough (stdlib only). Optional: [gitleaks](https://github.com/gitleaks/gitleaks) for a local secret scan.

```bash
git config core.hooksPath .githooks   # runs `gitleaks protect --staged` if installed
```

CI always runs gitleaks even when the hook is not enabled.

## Rules

- Do not commit anything under `data/` except `.gitkeep` and `*.example.*`.
- Do not commit avatars, `.env`, `dist/`, or built `index.html`.
- Tests must not write to the real `data/` tree.
- Public HTML must pass `scripts/check_public_leaks.py`.
- UI copy stays English.
- Follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Pull requests

Keep changes small. Run the unittest suite and `bash scripts/check_no_real_data.sh` before you push.
