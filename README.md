# openIMIS Backend Coordination module

The Coordination module manages departmental **activities** on a shared calendar with a
multi-level maker-checker approval workflow (submitter → manager → Coordination Officer →
Coordination Manager) and a cross-module **unified calendar** that also surfaces Training
and Communications events.

Built on the openIMIS core conventions (HistoryModel, per-entity mutation journaling,
`BaseService`, rights-config + `post_migrate` seeding). It is the backend counterpart of
`openimis-fe-coordination_js`.

## Entities

- `Department` — the department / unit an activity belongs to.
- `Activity` — Title, department, dates, location, venue, responsible person, status.

## Status workflow

`DRAFT → SUBMITTED → MANAGER_APPROVED → OFFICER_APPROVED → APPROVED`
(plus `REJECTED` / `CANCELLED`). One approve right per hop; enforced server-side by
`ActivityService.transition` + `STATUS_TRANSITIONS`.

## Rights (block 2511xx)

| Right  | Meaning                        |
|--------|--------------------------------|
| 251101 | activity search                |
| 251102 | activity create                |
| 251103 | activity update                |
| 251104 | activity delete                |
| 251110 | manager approve                |
| 251111 | coordination officer approve   |
| 251112 | coordination (dept) approve    |
| 251201 | department search              |
| 251202 | department manage              |
| 251601 | dashboard / calendar view      |
| 251901 | coordination settings admin    |

## Install

Add to the assembly `openimis-be_py/openimis.json` `modules` (after `core`, `location`):

```json
{ "name": "coordination", "pip": "-e /abs/path/openimis-dist_dkr/openimis-be-coordination_py" }
```

Then:

```bash
pip install -e /abs/path/openimis-dist_dkr/openimis-be-coordination_py
python manage.py makemigrations coordination
python manage.py migrate
```

Rights are seeded to the IMIS Administrator role on `post_migrate`.
