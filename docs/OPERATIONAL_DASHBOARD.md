# Operational dashboard review

## Gaps addressed

- Provider freshness was not prominent and could remain labelled current indefinitely. The dashboard now derives freshness from the provider timestamp, shows the last check separately, and ages into stale state.
- Operators lacked a read-only refresh action. Manual refresh and optional one-minute refresh update the screen without creating database records; background tabs pause polling.
- The map, rainfall and gauge information were visually disconnected. The dashboard now has compact rainfall cards, threshold comparison bars, a map, current drivers and gauge status.
- Issued area advisories were buried in another screen. A scoped advisory list links to the existing response workflow.
- History only exposed raw JSON. Risk-level filtering, snapshot expansion and CSV export now use stored assessments. CSV carries source/profile timestamps and protects spreadsheet formula cells.
- A missing short-duration input suppressed valid longer-duration windows. Each window now evaluates independently while the overall incomplete screen stays UNKNOWN.
- Draft creation relied on a previously saved current-state flag. It now rechecks provider timestamp and catchment configuration. The UI also expires the draft action after 15 minutes.
- Flood SMS could be rewritten as landslide text. Reviewed flood wording is preserved in every language preference; no unreviewed automatic translation is invented.
- Flood and provider regressions were not included in CI. Backend flood/recovery tests, browser checks and view-level integrity checks are now included.

## Still needed for validated prediction

This update does not create a calibrated forecast model. Local event/non-event inventories, verified basin boundaries, basin-average rainfall, streamflow observations, regional validation, measured warning lead time and authoritative exposure/road-closure layers remain data and research work. Generic automatic screening remains labelled uncalibrated. A settlement marker is not an inundation boundary. A provider-derived coarse terrain gradient is not a surveyed local slope.

SMS delivery still requires the configured provider; no real messages were sent during this work. No field gauges were fabricated or enrolled. PostgreSQL integration is verified by the storage CI job rather than a production database test.
