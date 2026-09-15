# Privacy and configuration policy

This repository is public. Treat the Git history as permanently public.

## Never commit

- research datasets, samples, researcher exports, media, transcripts, embeddings, or derived row-level data;
- CSV/TSV/JSONL/Parquet/SQLite/DuckDB files containing research data;
- `.env` files, API tokens, database URLs with credentials, S3 credentials, SSH keys, certificates, cookies, or session material;
- CSC project paths, private bucket names, internal hostnames, usernames, or project-specific configuration unless deliberately sanitized for publication;
- screenshots or dashboard exports that expose private data.

The root `.gitignore` blocks common data and secret formats. This is a safety net, not a substitute for checking `git status` before every commit.

## What may be committed

- source code and tests using synthetic fixtures;
- `.env.example` with placeholders only;
- schema documentation and public interchange contracts;
- configuration examples that contain no credentials, private paths, project IDs, unpublished codebooks, or sensitive identifiers.

## Runtime profiles

The default `local` profile uses local files, SQLite, in-memory caching, and the local filesystem. It must work without network access or external services.

A `server` deployment may opt into MongoDB for analysis records, Redis for caching/state, and S3-compatible object storage such as CSC Allas. Remote credentials must be supplied through environment variables or another secret manager outside the repository.

## If a secret or private dataset is committed

1. Rotate/revoke the credential immediately when applicable.
2. Remove the file from the current branch.
3. Purge it from Git history if the material must not remain public.
4. Review logs, forks, releases, Actions artifacts, and caches for copies.
5. Do not rely on a later `.gitignore` rule to make an already-committed file private.
