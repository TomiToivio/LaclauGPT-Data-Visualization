# Study deployment patterns

This repository is public code. Real corpora, review databases, private hostnames, credentials, CSC project identifiers and concrete machine paths remain outside Git.

## AI26 near-real-time visualization on the analysis server

For a same-machine Collection -> Analysis -> Visualization deployment, point Visualization at the study-specific Analysis output directory:

```bash
export LACLAUGPT_VIS_ANALYSIS_DATA_DIR=/private/analysis/ai26
export LACLAUGPT_VIS_DATA_DIR=/private/visualization/ai26
export STREAMLIT_SERVER_PORT=18501
scripts/run_private_dashboard.sh
```

The paths and port are placeholders. Keep the real values in private deployment configuration.

The Monitor tab already provides the generalized AI26 live view: corpus size, analyzed/awaiting counts, latest timestamps, formations, signifiers and actors. Streamlit reruns refresh local-file inputs; MongoDB can be used when a distributed live store is preferable.

By default the launcher binds Streamlit to loopback. Reach it from a researcher workstation using authenticated SSH forwarding or place it behind an authenticated reverse proxy configured outside this repository:

```bash
ssh -N -L 18501:127.0.0.1:18501 RESEARCH_SERVER
```

A private overlay network (such as a WireGuard-based mesh) is also an acceptable approved access layer. In that case bind the service to the overlay interface address rather than `0.0.0.0` — the preflight deliberately refuses a wildcard bind, and binding the overlay address keeps the socket off the LAN, loopback and container bridges while remaining reachable by mesh peers. Run the service under a supervising unit (for example a `systemd --user` unit with lingering enabled) rather than an ad-hoc background process, so it survives session end; an unsupervised launch stops when its parent session does.

Do not expose a research dashboard containing row-level data directly to the public Internet.

## EP24 visualization on CSC Pouta

Pouta should run the same application rather than an EP24-specific dashboard fork. Stage the private canonical/researcher output from the Roihu reprocessing workflow into a private Pouta-visible directory, or configure the optional MongoDB backend.

Local-file pattern:

```bash
export LACLAUGPT_VIS_ANALYSIS_DATA_DIR=/private/ep24/analysis
export LACLAUGPT_VIS_DATA_DIR=/private/ep24/visualization
export STREAMLIT_SERVER_PORT=18502
scripts/run_private_dashboard.sh
```

The Researcher Review tab is the generalized EP24 workbench. Historical flat EP24 exports are accepted only through the bounded legacy adapter; new reprocessing output should prefer the canonical nested record contract so transcript, OCR, multimodal/frame evidence, summary, structured analysis, uncertainty, provenance and review state remain interoperable.

For Pouta networking, keep the application loopback-only unless the private deployment explicitly adds an authenticated TLS reverse proxy or another approved access layer. Security-group rules, floating IPs, DNS names, credentials and certificates are operational secrets/configuration and must not be committed.

## Study isolation

Use a different `LACLAUGPT_VIS_DATA_DIR` per study. This keeps review SQLite databases, uploads, caches, exports and temporary artifacts from AI26 and EP24 separate even when the application code is identical.

Recommended private layout:

```text
<private-root>/
  ai26/
    analysis/
    visualization/
  ep24/
    analysis/
    visualization/
```

The public repository intentionally does not prescribe the real root, host, CSC project, bucket, database URI or service port.

## Data handoff

Preferred paths are:

```text
AI26 on one server:
Collection canonical JSONL -> Analysis incremental output -> Visualization

EP24 across CSC systems:
Roihu private reprocessing -> private transfer/shared storage -> Pouta Visualization
```

CSV/JSONL remains the manual fallback. MongoDB + Redis + S3-compatible object storage may be used for distributed deployments, but backend choice must not change canonical `source_url`, provenance or review semantics.
