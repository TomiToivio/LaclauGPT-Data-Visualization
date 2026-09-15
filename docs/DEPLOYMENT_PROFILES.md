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
