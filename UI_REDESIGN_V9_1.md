# PRAHARI v9.1 — Minimalist Focused UI

The frontend has been redesigned around the selected **Minimalist Focused** concept while preserving the v9 backend, APIs, risk workflow, reports, alerts, data provenance, and roadmap modules.

## What changed
- Dark compact left navigation on desktop; responsive compact navigation on tablets/mobile.
- Global location search moved into a clean utility header.
- Overview redesigned as a simple situation page: hero context, current assessment, four meaningful summary cards, four quick actions, assessment explanation, and map preview.
- Primary navigation remains: Overview, Risk Map, Reports & Alerts, Data & Settings.
- Risk state always includes text labels in addition to color.
- Live/replay state remains explicit in the utility bar and data cards.
- Existing report and alert lifecycle controls remain functional.
- Existing GIS, research, IoT, infrastructure, satellite and data-source modules are retained; advanced modules remain under progressive disclosure where appropriate.
- Responsive breakpoints were reworked for desktop, tablet and mobile.
- Decorative gauges, glowing panels, excessive gradients and repetitive AI labels are not used.

## Files changed
- `frontend/src/App.jsx`
- `frontend/src/style.css`
- `frontend/public/prahari-hero.png`

## Verification
- Backend regression suite: **11 passed**.
- Frontend source was structurally reviewed after the redesign.
- npm dependency installation in the build environment timed out, so the final Vite bundle must be built on a machine with npm registry access using `npm install` then `npm run build`.
