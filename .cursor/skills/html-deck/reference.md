# HTML deck — template reference

## Template file

- **Workspace copy:** `.cursor/skills/html-deck/cisco-thousandeyes-deck-template.html`
- **User download:** `~/Downloads/Cisco ThousandEyes - HTML Presentation Template(1).html`

## Slide component quick reference

| Class | Purpose |
|-------|---------|
| `.slide.cover` | Title / cover |
| `.slide.statement` | Big quote (only gradient-allowed slide) |
| `.slide.edge` | Standard content slide with left accent bar |
| `.band` + `.stage` | Horizontal workflow stages |
| `.cband` + `.cgrid` + `.pcard` | 2/3/4-up card grid |
| `.ucband` + `.ucgrid` + `.uccard` | Assurance play coverage (`.ucdot` adopted/partial/none) |
| `.bvband` + `.bvrow` | Numbered business-value objectives |
| `.slide.seg` | Section divider / segue |
| `.slide.agenda` | Agenda with section groups |
| `.slide.gfxonly` + `.gfxstage` | Full-bleed diagram or screenshot |
| `.ucase` + `.gfx` | Split: copy left, diagram right |
| `.doc` + `.drow` | Documentation links |
| `.slide.closing` | Thank-you / closing |

## SVG diagram grammar (`.te` toolkit)

| Class | Meaning |
|-------|---------|
| `.ac` + `.glow` | Active path under test (Cisco Blue) |
| `.ln` / `.ln2` | Muted context links |
| `.bx` / `.bxa` | Outlined / accented container |
| `.dotw` / `.dota` / `.dot` | Node variants |
| `.topo` (on svg) | Mute entire topology to greys |
| `.rca` (on svg) | Enable red/amber fault localization |

Gallery diagrams in the template appendix: hub-and-spoke, convergence, multi-path egress, cloud vantage, RCA, telemetry fan-out, self-healing loop, etc. Copy and relabel — do not hand-roll colors.

## Typography (use `.t-*` classes)

- `.t-h1` — 53px Medium (titles)
- `.t-h2` — 32px Medium
- `.t-body` — 21px Regular (default body)
- `.t-label` — 16px labels
- `.t-link` — underlined links

## ThousandEyes MCP (user-global-demo)

When the user provides IDs or asks to pull live/demo data:

| Need | Tool direction |
|------|----------------|
| Test metadata / results | `get_network_app_synthetics_test`, `get_detailed_test_results` |
| Path visualization | `get_path_visualization_results`, `get_full_path_visualization` |
| Dashboards | `get_dashboard`, `get_dashboard_widget_data`, `list_dashboards` |
| Alerts / events | `list_alerts`, `get_alert`, `list_events` |
| Outages | `search_outages` |
| Instant test demo | `run_*_instant_test` + `get_instant_test_metrics` |

Sanitize customer-specific data in external-facing decks; label demo/synthetic data when appropriate.

## Assurance plays (for `.uccard` rows)

Default six plays in the sample deck — adapt labels to customer language:

1. Workforce Digital Experience
2. Network / WAN / SD-WAN
3. Internet & BGP / routing
4. SaaS & critical apps
5. Cloud & hybrid infrastructure
6. AgenticOps / observability integration

Set adoption per row: `.ucdot.adopted` | `.partial` | `.none` (shape + color, never color alone).
