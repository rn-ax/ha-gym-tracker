# ha-gym-tracker

A Home Assistant **custom integration** (`custom_components/gym_tracker/`) that turns a calendar of workout events into three sensors (total sessions, day streak, cost per session), plus zone-based auto-detection that creates those calendar events without any manual logging.

## Architecture

Everything is event-driven through a `DataUpdateCoordinator` with `update_interval=None` — there is no polling. A refresh is triggered by:

- The tracked `person` entity entering or leaving a configured gym `zone` (a 5-minute debounce on entry, none on exit — matching the zone-detection automations this integration replaces).
- The configured `calendar` entity's native `calendar.add_event` / `calendar.remove_event` events, so a manually-added calendar entry (a walk, a gym visit typed in by hand) is picked up the same way an auto-detected one is.
- A daily tick just after midnight, so the streak sensor actually decays to 0 the day after a missed day instead of staying frozen until the next calendar change.

All three sensors' actual math lives in `calculations.py`, which has zero Home Assistant imports on purpose — it's what `tests/test_calculations.py` exercises directly, no HA test harness needed.

## Caching

Calendar data older than ~3 months is treated as immutable and folded into a `homeassistant.helpers.storage.Store`-backed cache (`{cutoff, gym_sessions_before_cutoff, gym_sessions_by_year_before_cutoff}`) rather than re-fetched on every refresh. Every refresh only queries `calendar.get_events` for `[cutoff, now]`; the daily tick is what advances `cutoff` forward and folds the newly-immutable window into the cache. The `gym_tracker.rebuild_cache` service resets `cutoff` to the epoch and forces a full recompute — the escape hatch for the one real risk here: editing or deleting a calendar event older than the cutoff silently desyncs the cache otherwise, since nothing else re-checks that range.

## Config vs. options

The config flow (`calendar_entity`, `tracked_person`, `gym_zones`) has no defaults — this is meant to be a generic, shareable integration, not one hardcoded to any specific household's entities. Cost is tracked separately, per month (`entry.options["monthly_costs"]["YYYY-MM"]`), since it's billed monthly and can change mid-year. A missing current-month cost raises a fixable issue via `homeassistant.helpers.issue_registry` (see `repairs.py`) rather than just leaving `sensor.gym_cost_per_session` silently unavailable — the fix flow and the options flow share the exact same form (`config_flow.monthly_cost_schema`) so they can't drift apart.

## Where this deploys

This integration's code goes to `/config/custom_components/gym_tracker/` on whatever machine runs Home Assistant, installed as a HACS custom repository (`hacs.json` has no `zip_release` — HACS archives whatever's on `main` directly, no build/release step needed).

## Legacy entity_ids

`sensor.gym_sessions_total`, `sensor.gym_session_streak`, and `sensor.gym_cost_per_session` deliberately match the entity_ids from the AppDaemon apps this integration replaces (`_attr_has_entity_name = False` with a name that slugifies to the same id), so existing dashboards keep working across the migration. `binary_sensor.gym_session_ongoing` is new — it replaces `input_boolean.gym_session_ongoing` from the old zone-detection automations, and carries a `session_start` attribute for a possible future iOS Live Activity automation to use.

## Integration structure

```
custom_components/gym_tracker/
  __init__.py       # entry setup/unload, registers the rebuild_cache service
  manifest.json      # domain, config_flow: true
  const.py           # DOMAIN and shared constants
  calculations.py     # pure logic: streak, date dedup/filtering, cost math -- no HA imports
  coordinator.py      # event-driven DataUpdateCoordinator: zone detection, calendar listening, daily tick, caching
  config_flow.py      # setup form + options flow (monthly cost) + the shared schema repairs.py reuses
  repairs.py          # fix flow for the "missing current month's cost" issue
  sensor.py            # the three legacy-entity_id sensors
  binary_sensor.py     # session-ongoing sensor
  services.yaml         # rebuild_cache service definition
```
