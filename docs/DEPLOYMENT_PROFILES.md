# Deployment profiles

Visualization has one canonical application and input contract. Machine, execution and storage topology are configuration dimensions.

| Use | machine | execution | storage | records | cache | objects |
| --- | --- | --- | --- | --- | --- | --- |
| Research laptop | `laptop` | `cli` | `local` | files/SQLite | memory | local filesystem |
| Linux website | `linux-server` | `web-service` | `local` | files/SQLite | memory | local filesystem |
| Distributed website | `linux-server` | `web-service` | `distributed` | MongoDB | Redis | S3/CSC Allas |
| Agent operation | any | `agent` | local/distributed | same loaders | same cache | same object store |

The convenience `profile=server` maps an otherwise-default laptop/CLI configuration to Linux/web-service. Explicit dimensions remain the preferred interface.

## Laptop / CLI

Configure `LACLAUGPT_VIS_ANALYSIS_DATA_DIR` to the Analysis module's private `data/` root or to a prepared canonical export. Do not guess repository paths. Run:

```text
laclaugpt-visualize profile
laclaugpt-visualize health
laclaugpt-visualize serve
```

CSV, JSONL, JSON, Parquet and SQLite remain supported local/manual-transfer inputs. CSV/JSONL is the manual cross-machine fallback.

## Linux web service

Set `machine=linux-server`, `execution=web-service`, a private runtime `data_dir`, and a bind host/port in external deployment configuration. Keep the application behind the site's normal authentication/reverse-proxy/TLS layer; real domains and certificates do not belong in this repository.

`laclaugpt-visualize health` performs an offline readiness check. It validates configuration, the configured Analysis path, output-path containment, and the existing rule that interactive visualization must not run inside Slurm/Roihu allocations.

A generic systemd template is provided in `deploy/laclaugpt-visualization.service.example`. Replace placeholders in private deployment configuration. Logs, cache, exports, artifacts and run audit files stay beneath the configured private `data/` tree.

## Verifying a running deployment

A service that is `active` and answers `200` is not evidence that the reviewed code is what is serving: that
mistake has produced four incidents (#176, #185, #234, and a live unit found running six commits behind
`main` while its health endpoint returned `ok`). "Did my deploy work?" is four questions, and each of them
has been answered wrongly at least once:

1. is the unit running, and from which working directory;
2. is that checkout the reviewed commit on the expected branch;
3. which export snapshot is the data directory actually holding;
4. does the port answer on `/_stcore/health`, and is the access gate on or off.

`deploy/report-served-state.py` asks all four, read-only, and exits non-zero if any answer is a problem:

```text
python deploy/report-served-state.py \
    --unit laclaugpt-visualization.service \
    --repo /srv/laclaugpt/visualization \
    --data-dir /srv/laclaugpt/private/analysis/<study>/dashboard/export \
    --port 8501
```

```text
[ok  ] unit      laclaugpt-visualization.service active, from /srv/laclaugpt/visualization, password set
[FAIL] checkout  main at 6a510b1
        - serving 6a510b1, origin/main is 89705f8 (0 ahead / 6 behind)
[ok  ] data      fiplpt_500_20261115 run=monday500_20261031 videos=1500 over 3 countries
[ok  ] health    http://127.0.0.1:8501/_stcore/health -> 200 'ok'

3/4 checks ok
```

Run it **before** a deploy (to know what you are replacing) and **after** it (to know what you got). Add
`--json` to record the state with a deployment, and `--no-fetch` only when the host cannot reach the remote —
without a fetch, a stale `origin/main` ref makes a behind checkout look current, which is itself a test.

Notes on the design:

* A drift check is only as good as the fetch. `tests/test_served_state.py` pins that blindness rather than
  pretending it away.
* A snapshot without `manifest.json`/`MANIFEST.json` is not a snapshot, and a total that hides a missing
  country is not a count — both are reported as problems even while the app renders happily.
* A password is reported as `password set`; the value is never read, printed or logged.
* The tool is study-neutral. Host, unit, port and paths are arguments; the deployment state of a specific
  instance belongs in private deployment configuration, not in this repository.

## Distributed storage

For `storage=distributed`, configure:

- `data_backend=mongodb`
- `cache_backend=redis`
- `object_backend=s3`

The project namespace contract keeps projects isolated: MongoDB collections are project-prefixed, Redis keys are project-scoped, and S3/Allas objects live below `projects/<project_id>/...`. Mongo `_id` is never canonical identity; `source_url` remains canonical. S3 object URIs are references from canonical records rather than a second record schema.

## Hermes / agents

Hermes uses `laclaugpt_visualization.integrations.hermes`, which delegates to the same configuration and canonical loaders as human operation. See `HERMES.md` and `skills/laclaugpt-data-visualization/SKILL.md`.

## Privacy boundary

Do not commit research rows, review databases, exports, credentials, private endpoints, domains, TLS keys, CSC project identifiers, machine-specific paths or service secrets. Public examples use placeholders only.
