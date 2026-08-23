# SEO Skills

Reusable Agent Skills for SEO research workflows.

## Skills

- `keyword-root-library` — maintains a reusable keyword-root library and evidence lifecycle for demand discovery.
- `emerging-keyword-monitor` — detects and monitors newly observed demand, breakout growth, and emerging search expressions, then routes evidence downstream without making final SEO selection decisions.
- `seo-keyword-selection` — runs the downstream SEO keyword opportunity selection workflow from roots/seeds through metric screening, KGR/SERP validation, clustering, and decision support.

Together, the boundary is: root library = **what demand space exists**; emerging monitor = **what demand is forming or changing now**; keyword selection = **what is worth pursuing**.

## Repository layout

```text
skills/
  keyword-root-library/
  emerging-keyword-monitor/
  seo-keyword-selection/
```

Each skill is self-contained and includes its own `SKILL.md`, references, scripts, and tests. The monitor and selection skills reference root handoffs; neither duplicates the canonical root-library asset.

## Validation

Run tests from the repository root:

```bash
python3 -m pytest skills/keyword-root-library/tests/test_root_library.py -q
python3 -m pytest skills/seo-keyword-selection/tests/test_selection.py -q
python3 -m pytest skills/emerging-keyword-monitor/tests -q
python3 -m pytest -q
```
