# SEO Skills

Reusable Agent Skills for SEO research workflows.

## Skills

- `keyword-root-library` — answers what reusable demand space exists and maintains the canonical root library and evidence lifecycle.
- `emerging-keyword-monitor` — detects newly observed, accelerating, or newly expressed search demand from time-series evidence and routes verified emerging signals downstream without making final SEO selections.
- `seo-keyword-selection` — evaluates which keyword opportunities are worth pursuing using real metrics, KGR/SERP validation, clustering, and decision rules.
- `seo-page-keyword-mapping` — maps a predefined page/entity universe to ownership-confirmed Primary/Secondary keywords, demand clusters, content modules, and child-URL candidates.

## Repository layout

```text
skills/
  keyword-root-library/
  emerging-keyword-monitor/
  seo-keyword-selection/
  seo-page-keyword-mapping/
```

Each skill is self-contained and includes its own `SKILL.md`, references, scripts, and tests. The canonical `root-library.csv` exists only under `keyword-root-library`; other skills reference roots by handoff or `root_id` and never duplicate that asset.

## Validation

Run the four skill suites and then the repository-wide suite:

```bash
python3 -m pytest skills/keyword-root-library/tests/test_root_library.py -q
python3 -m pytest skills/seo-keyword-selection/tests/test_selection.py -q
python3 -m pytest skills/emerging-keyword-monitor/tests -q
python3 -m pytest skills/seo-page-keyword-mapping/tests -q
python3 -m pytest -q
```

The four responsibilities remain separate: root-library defines reusable demand space, emerging-keyword-monitor identifies demand that is forming or changing, seo-keyword-selection owns final SEO opportunity decisions, and seo-page-keyword-mapping assigns confirmed demand to planned URLs and page architecture.
