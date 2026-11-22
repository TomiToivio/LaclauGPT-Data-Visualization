# AI26 Laskin dashboard acceptance (22 November 2026)

**Scope:** host verification after the AI26 Visualization readability/reliability repair.
Repository CI and a healthy Streamlit port do **not** prove that Laskin is serving the
correct checkout, correct module, or current MongoDB research results.

## Host operator: read-only inspection before any deployment

Perform outside a running worker/deploy window and avoid touching a dirty checkout.
Do not print or commit private environment files or documents.

```bash
# After setting the private path locally; do not paste the path into public issues.
cd "$LACLAUGPT_VIS_REPO_ROOT"
git status --short
git rev-parse HEAD
git rev-parse origin/main
git worktree list
.venv/bin/python deploy/served-drift-report.py --json
.venv/bin/python -m compileall -q src
curl --fail --silent --show-error http://127.0.0.1:8501/_stcore/health
```

Record the full deployed Git SHA, service name, process command and port. If this
is a system service, inspect `systemctl status laclaugpt-visualization-ai26`
and sanitized `journalctl` output; use `systemctl --user` only when the
service was explicitly installed as a user service. Check the actual
`/proc/<pid>/cwd`, not just the checkout in the terminal.

## Safe deployment and acceptance

1. Only after verifying no active write/deploy and a clean checkout, fast-forward
   the intended `main` working tree to the reviewed merge. Never hard-reset or
   steal a branch from a second worktree.
2. Execute `deploy/preflight-laskin-ai26.sh` with the private environment
   loaded through the normal service manager. Restart the *confirmed* AI26
   service using the existing operator process, not an unverified service name.
3. Check that Streamlit reports health on the documented loopback port **and**
   that the rendered title is **LaclauGPT · AI26 Research Dashboard** rather
   than the legacy generic workbench.
4. Verify the corpus-level **Collected** and **Stored analyses** totals against
   sanitized MongoDB aggregate counts from the canonical `ai26__records` and
   `ai26__analysis_results` collections. Verify a bounded result window
   contains actual recent records (not only legacy `ai26__analyzed`).
5. Check the Monitor freshness warning against a safe aggregate of
   `created_at` values, including both BSON datetime and historical float
   epoch rows. The newest visible age should not be misrepresented as
   full-corpus completeness.
6. Explore with multi-label formations, search special characters such as
   `[`, review the top-label chart ordering, and close-read a row with missing
   metadata or list-valued text. Ensure no page exception or unreadable chart.
7. Verify Networks/Records/Reports tabs and optional Redis operations do not
   expose credentials or require S3/Allas for the AI26 text-only profile.
   MongoDB and Redis remain required in the distributed profile.
8. Capture only SHA, health status, aggregate counts, timing, redacted logs,
   and human UI observations. A 200 response by itself is insufficient.

**Expected outcome:** evidence of the right code being served, representative
manual view checks, and correct source of analysis data. Nothing in this
repository-only change is proof that steps 1–8 ran on Laskin.
