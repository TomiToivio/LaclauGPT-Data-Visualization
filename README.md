# LaclauGPT Data Visualization

> [!IMPORTANT]
> **Current development phase: Phase 1.** `phase-1` is the canonical active development/stable branch, and `main` MUST match its current validated state. The `phase-0` branch remains the preserved Phase 0 baseline only; Phase 2–4 stay isolated until explicitly promoted.

[![tests](https://github.com/TomiToivio/LaclauGPT-Data-Visualization/actions/workflows/tests.yml/badge.svg)](https://github.com/TomiToivio/LaclauGPT-Data-Visualization/actions/workflows/tests.yml)

> **Part of the [LaclauGPT](https://github.com/TomiToivio/LaclauGPT) project.** The main LaclauGPT repository is the **meta-repository** and project front door: it contains the scientific paper, theory, shared architecture, canonical data contract and complete-system documentation. This repository is only the **Data Visualization** implementation stage.
>
> **Project map:** [LaclauGPT / paper + meta-repo](https://github.com/TomiToivio/LaclauGPT) → [Data Collection](https://github.com/TomiToivio/LaclauGPT-Data-Collection) → [Data Analysis](https://github.com/TomiToivio/LaclauGPT-Data-Analysis) → **Data Visualization (you are here)**

**LaclauGPT** is an open social-science research framework for **LLM-assisted computational discourse analysis** of large textual and multimodal corpora. It combines computational methods with interpretive political research while keeping model outputs traceable to source evidence, uncertainty, provenance and human review.

The current flagship research programme is **[LaclauGPT: Ideological contestation over AI](https://github.com/TomiToivio/LaclauGPT/blob/main/paper/PHASE_1_PAPER.md)**. The canonical theoretical and methodological contract is **[THEORY.md](https://github.com/TomiToivio/LaclauGPT/blob/main/THEORY.md)**.

The framework is developed around Ernesto Laclau and Chantal Mouffe's discourse theory and Emilia Palonen's work on populism, polarisation and hegemonic dynamics. The AI/AGI study is the main development case, but LaclauGPT is a **general research framework rather than a single-purpose AI ideology classifier**. The same architecture can support election research, populism, grievance politics, social-media research and other comparative discourse-analysis projects.

> [!WARNING]
> **Human-in-the-loop academic research only.** LaclauGPT's machine-generated summaries, classifications, discourse-theoretical codes, signifier roles, ideological formations, affects and other interpretations are preliminary analyses that must be verified by a human researcher. They are not ground truth or autonomous scholarly judgement. LaclauGPT is designed for academic research, not autonomous operational, administrative, intelligence, moderation, profiling or policy decisions about people or groups.


<!-- project-background:start -->
## Project background and funding

LaclauGPT grew out of research-software work at the **[Helsinki Hub on Emotions, Populism and Polarisation (HEPPsinki)](https://www.helsinki.fi/en/researchgroups/emotions-populism-and-polarisation), University of Helsinki**, and has been developed in connection with the **CO3**, **PLEDGE**, and **ENDURE** international research projects.

<p align="center">
  <a href="https://www.co3socialcontract.eu/"><img src="https://www.co3socialcontract.eu/favicon.ico" width="88" height="88" alt="CO3 project logo"></a>
  &nbsp;&nbsp;&nbsp;&nbsp;
  <a href="https://www.pledgeproject.eu/"><img src="https://www.pledgeproject.eu/favicon.ico" width="88" height="88" alt="PLEDGE project logo"></a>
  &nbsp;&nbsp;&nbsp;&nbsp;
  <a href="https://www.endure-project.org/"><img src="https://www.endure-project.org/favicon.ico" width="88" height="88" alt="ENDURE project logo"></a>
</p>

<p align="center"><strong>🇪🇺 European Union</strong></p>

- **[CO3 — Continuous Construction of Resilient Social Contracts Through Societal Transformations](https://www.co3socialcontract.eu/)** studies how more democratic, inclusive and resilient social contracts can be built and renewed.
- **[PLEDGE — Politics of Grievance and Democratic Governance](https://www.pledgeproject.eu/)** studies the emotional dynamics of political grievances and democratic governance.
- **[ENDURE — Inequalities, Community Resilience and New Governance Modalities in a Post-Pandemic World](https://www.endure-project.org/)** examines inequalities, community resilience and governance after COVID-19.

**Funding.** CO3 and PLEDGE have been funded in the **Horizon Europe framework of the European Union (2024–27)**. ENDURE was a **Trans-Atlantic Platform funded consortium**; the work at the **University of Helsinki was funded by the Research Council of Finland (2022–25)**.

The original LaclauGPT pipeline was used in the **2024 European Parliament election** research programme to collect and analyse multimodal TikTok and Instagram material across multiple European countries. The present modular framework generalises that work into reusable Data Collection, Data Analysis and Data Visualization components.

<!-- project-background:end -->

## Research philosophy: human-in-the-loop as an assemblage

LaclauGPT uses a deliberately assemblage-based working philosophy of AI:

> **AI = HUMAN + LLM + LANGUAGE + INTERNET**

This is a methodological and philosophical framing, not a settled empirical claim about machine consciousness.

- **HUMAN — interpretation and accountable agency.** Researchers choose questions, define concepts and codebooks, evaluate evidence, resolve ambiguity and remain responsible for conclusions.
- **LLM — learned model plus agentic machinery.** Models may contribute structured proposals, retrieval, comparison and tool use, but their outputs remain fallible and provisional.
- **LANGUAGE — communication protocol and cognitive medium.** Language couples the researcher, model, sources and theoretical concepts, and helps structure the distinctions and relations available to analysis.
- **INTERNET — infrastructure and epistemic environment.** Networks, software, model repositories, databases, APIs and research corpora form part of the practical research system. Retrieved information remains evidence to evaluate.

Human-in-the-loop therefore means more than a final approval step. The human researcher is constitutive of the research process throughout.

## Theoretical and methodological orientation

LaclauGPT treats political meaning as relational, contested and only partially fixed. Its purpose is not merely to count topics or visualize model confidence, but to help researchers inspect evidence-linked proposals about articulations, identities, signifiers, political frontiers and ideological formations.

Theoretical concepts such as nodal points, floating and empty signifiers, equivalence, antagonism, affective investment, populist articulation and hegemony must not be inferred from visual prominence alone. **Frequency is not hegemony; graph degree is not nodal status; proximity in a layout is not equivalence; sentiment is not affective investment; and a two-cluster picture is not by itself polarisation.**

Visualization therefore supports interpretation rather than replacing it. Researchers must be able to move from aggregate patterns back to records, evidence, provenance, uncertainty and review status.

See the **[scientific paper](https://github.com/TomiToivio/LaclauGPT/blob/main/paper/PHASE_1_PAPER.md)** and **[theory contract](https://github.com/TomiToivio/LaclauGPT/blob/main/THEORY.md)** for the full conceptual framework.

## This repository

**LaclauGPT Data Visualization** is the canonical researcher-facing visualization and review implementation in the modular LaclauGPT architecture. It consumes canonical records from **[LaclauGPT Data Collection](https://github.com/TomiToivio/LaclauGPT-Data-Collection)** and analytical enrichments from **[LaclauGPT Data Analysis](https://github.com/TomiToivio/LaclauGPT-Data-Analysis)**. The scientific paper, theory and project-wide contracts live in the **[LaclauGPT meta-repository](https://github.com/TomiToivio/LaclauGPT)**.

It provides one researcher-facing application with Monitor, Researcher Review, and Explore modes. It does not perform collection or discourse inference itself.

## Unified application

- **Monitor**: near-real-time corpus status, analyzed/awaiting-analysis counts, latest source/analysis timestamps, formations, signifiers, actors and descriptive activity summaries.
- **Researcher Review**: one-record close reading with transcript, OCR, multimodal/frame evidence, human-readable summary, structured analysis fields, provenance, uncertainty, typed corrections, notes and rerun/reprocess requests.
- **Explore**: shared filters, timelines, formation/topic/entity distributions, relation tables and graph-projection inputs.

Counts, model confidence, graph degree and layout are descriptive aids. They do not by themselves establish hegemony, nodal status, empty/floating signification, antagonism or theoretical validity.\n\nPhase 1 also restores SNA visualization as an isolated downstream capability: it renders only an explicit upstream `NETWORK` product, preserves source/evidence provenance, and stays unavailable when Analysis has not supplied a stable network result. Visualization does not compute social ties, centrality, communities, or missing network structure. See `docs/PHASE1_SNA_VISUALIZATION.md`.

## Legacy / Specialized dashboards

The EP24-derived **pledge** and **art** dashboards intentionally bypass the complete modern canonical pipeline. They use privacy-safe, deterministic legacy adapters and a shared `legacy-view-v1` interchange contract:

- Python preserves raw values, performs deterministic normalization and records provenance;
- R independently checks important aggregates and produces research-readable static figures;
- JavaScript provides linked interaction and the art dashboard's research/exhibition rendering modes.

Political metadata distinguishes `observed`, `legacy_derived` and `missing` values. The art renderer explicitly labels orbital/constellation geometry as decorative unless a documented private-runtime semantic projection is supplied. Real legacy datasets, row-level derivatives, embeddings and private configuration remain outside Git.

See [`docs/LEGACY_SPECIALIZED_DASHBOARDS.md`](docs/LEGACY_SPECIALIZED_DASHBOARDS.md).

## Canonical data boundary

```text
LaclauGPT-Data-Collection
        ↓ canonical records
LaclauGPT-Data-Analysis
        ↓ canonical analysis results
LaclauGPT-Data-Visualization
```

The shared contract governing that flow lives in the **[LaclauGPT meta-repository](https://github.com/TomiToivio/LaclauGPT)**.

Canonical nested JSON/JSONL is primary. Stable `source_url`, schema version, provenance, review status, uncertainty/abstention and multimodal references are preserved into the visualization view model. Historical EP24 flat exports are supported only through `legacy_ep24.py`; legacy column names never become the core schema.

## Runtime data boundary

All runtime and study-specific material lives under `data/`, which is entirely excluded from Git. Common locations include `data/logs/`, `data/database/`, `data/config/`, `data/files/`, `data/csv/`, `data/jsonl/`, `data/cache/`, `data/exports/`, `data/artifacts/` and `data/tmp/`. Researcher reviews default to `data/database/reviews.sqlite3`.

Never commit row-level EP24/AI26 data, transcripts, OCR, media, researcher notes, review databases, caches, filtered exports, `.env`, Streamlit secrets, credential-bearing URIs, private hostnames or machine-specific paths.

## Local same-machine pipeline

```bash
export LACLAUGPT_VIS_ANALYSIS_DATA_DIR=../LaclauGPT-Data-Analysis/data
python -m pip install -e '.[dev]'
laclaugpt-visualize
```

Local operation requires no services: CSV/JSON/JSONL/SQLite plus local filesystem and the SQLite review store are sufficient.

## Distributed pipeline

Install remote adapters with:

```bash
python -m pip install -e '.[remote]'
```

MongoDB may carry canonical records, Redis may provide cache/pub-sub/state, and S3-compatible storage such as CSC Allas may carry referenced artifacts. All are optional and lazy. CSV/JSONL remains the manual cross-machine fallback.

## Architecture

```text
src/laclaugpt_visualization/
  app.py              # page orchestration only
  canonical.py        # public canonical record boundary
  data.py             # loaders, normalization, filters
  legacy_ep24.py      # bounded legacy compatibility
  transforms.py       # pure monitor/explore view models
  review/             # typed review model + SQLite/Mongo stores
  storage.py          # optional remote adapters
  config.py
```

See `docs/UNIFIED_DASHBOARD.md` and `docs/MIGRATION_REPORT.md` for feature mapping from the public visualization subtree, AI26 live dashboard and EP24 researcher dashboard.

## Privacy and quality

Normal CI is fully synthetic/offline and runs the public-tree privacy guard, Ruff and pytest on Python 3.11, 3.12 and 3.13.

```bash
python scripts/check_public_tree.py
ruff check .
pytest
npm run test:legacy
```

See `AGENTS.md`, `docs/PRIVACY_AND_CONFIGURATION.md`, and `docs/RUNTIME_DATA.md`.

## Where to go next

For collection/capture work, go to **[LaclauGPT-Data-Collection](https://github.com/TomiToivio/LaclauGPT-Data-Collection)**. For NLP/LLM/discourse-analysis work, go to **[LaclauGPT-Data-Analysis](https://github.com/TomiToivio/LaclauGPT-Data-Analysis)**. For the paper, theory, shared architecture or complete-system installation, return to **[LaclauGPT](https://github.com/TomiToivio/LaclauGPT)**.
