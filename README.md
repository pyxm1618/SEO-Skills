# SEO Skills

Reusable Agent Skills for SEO research workflows.

## Skills

- `keyword-root-library` — maintains a reusable keyword-root library and evidence lifecycle for demand discovery.
- `seo-keyword-selection` — runs the downstream SEO keyword opportunity selection workflow from roots/seeds through metric screening, KGR/SERP validation, clustering, and decision support.

## Repository layout

```text
skills/
  keyword-root-library/
  seo-keyword-selection/
```

Each skill is self-contained and includes its own `SKILL.md`, references, scripts, and tests.

## Validation

Run tests from each skill directory:

```bash
cd skills/keyword-root-library && pytest -q
cd ../seo-keyword-selection && pytest -q
```

The keyword-selection skill consumes root handoffs from `keyword-root-library`; it does not duplicate the root library asset.

<!-- bootstrap-trigger -->
