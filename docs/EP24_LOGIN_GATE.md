# Login gate on the researcher dashboard (#263)

`:8502` now requires a username and password, in the same shape as the legacy `:8501` dashboard: a
`streamlit-authenticator` config with `credentials.usernames[...]` and a cookie block, rendered before any export
is read.

## Where the credential lives

**Never in this repository.** The config file is outside it:

```text
$LACLAUGPT_VIS_AUTH_CONFIG          # explicit path, wins when set
~/.config/ep24-dashboard/auth.yaml  # default when the variable is unset
```

Created by the operator with mode `0600`, holding a **bcrypt hash**, not the password — the legacy `:8501` file
stores its password in clear text, which is one reason this one does not.

```yaml
credentials:
  usernames:
    <user>:
      email: ""            # optional; shown as "Signed in as ..." when set
      password: $2b$12$... # bcrypt
      roles: [researcher]
cookie:
  name: ep24_researcher_8502
  key: <random, generated once>
  expiry_days: 1
```

`tests/test_issue263_login_gate.py` fails if credential material ever appears in a tracked file, so a mistaken
commit is caught before it reaches a remote.

## What is gated

Every script, not just the landing page. Streamlit's navigation runs each page as its own script, so a gate on
the main app protects exactly one page; `pages/*.py` therefore call `require_login()` immediately after
`set_page_config` and before the first data read. A regression test asserts the call precedes
`_load_default_frame(`, `read_csv(`, `read_parquet(` and `load_data(` in every page.

State after deployment, measured with `AppTest` against the running checkout:

```text
GATED ep24_reprocessed_app.py          leaked_data=False
GATED 1_AI26_Multimethod_Explore.py    leaked_data=False
GATED 2_DNA.py                         leaked_data=False
GATED 3_SNA.py                         leaked_data=False
GATED Control_Plane.py                 leaked_data=False
GATED Graph_Context_Explorer.py        leaked_data=False
GATED rdf_explorer.py                  leaked_data=False
```

A wrong password shows the error and renders nothing; the correct one opens the dashboard. Both were exercised
through the deployed app, and the browser session was verified by hand.

## Turning it off, and rotating

* **Off:** remove `auth.conf` from the unit's `.d/*.conf` directory (or unset the variable) and restart. With no
  config and no `LACLAUGPT_VIS_DEMO_PASSWORD`, the app is open again — a deployment should not be able to be
  *accidentally* protected, so the state is explicit either way.
* **Rotate:** rewrite the file with a new hash and restart; sessions issued under the old cookie key remain valid
  until `expiry_days` passes, so rotating the `cookie.key` as well ends them immediately.

## The limitation worth stating plainly

The service speaks **HTTP, not HTTPS**. A password sent over HTTP crosses the network in clear text, so this gate
stops casual access and search-engine exposure, not an observer on the path. `:8501` has the same property. If the
dashboard is ever exposed beyond a trusted network, put it behind TLS (a reverse proxy with a certificate, or a
Tailscale-only bind) — the gate is not a substitute for that.
