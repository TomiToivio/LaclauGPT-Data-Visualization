"""Issue LaclauGPT#71 — the public NooPunk AI26 artifacts must exist and stay secret-free.

The NooPunk node is a second deployment of the same AI26 pipeline, so the risk this
file guards is not "does the runbook read well" but three concrete failure modes:

1. **Secrets leaking into a public repository.** The preflight and the runbook are
   the two new public artifacts; neither may contain a hostname, port, URI, bucket,
   account or credential.
2. **The two nodes drifting into two systems.** The NooPunk preflight must require
   exactly the same AI26 identity (project, browser contract) as Laskin's, and a
   different machine class — not a different database, bucket or project.
3. **The runbook promising controls that do not exist.** It documents a preflight
   and a wrapper; both must be present and executable, or the documentation is
   fiction.

Run: python3 -m unittest discover -s tests -p 'test_*.py'
"""
from __future__ import annotations

import stat
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

NOOPUNK_RUNBOOK = ROOT / "docs" / "AI26_NOOPUNK_DASHBOARD.md"
NOOPUNK_PREFLIGHT = ROOT / "deploy" / "preflight-noopunk-ai26.sh"
NOOPUNK_WRAPPER = ROOT / "scripts" / "ai26-noopunk.sh"
LASKIN_PREFLIGHT = ROOT / "deploy" / "preflight-laskin-ai26.sh"
LASKIN_RUNBOOK = ROOT / "docs" / "AI26_LASKIN_DASHBOARD.md"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class ArtifactsExistTests(unittest.TestCase):
    def test_runbook_preflight_and_wrapper_exist(self) -> None:
        for path in (NOOPUNK_RUNBOOK, NOOPUNK_PREFLIGHT, NOOPUNK_WRAPPER):
            with self.subTest(path=str(path.relative_to(ROOT))):
                self.assertTrue(path.exists(), f"{path.name} is missing")

    def test_shell_artifacts_are_executable(self) -> None:
        """A documented control that cannot be executed is documentation, not a control."""
        for path in (NOOPUNK_PREFLIGHT, NOOPUNK_WRAPPER):
            with self.subTest(path=path.name):
                mode = path.stat().st_mode
                self.assertTrue(mode & stat.S_IXUSR, f"{path.name} is not executable")

    def test_the_runbook_references_the_preflight_and_wrapper_by_real_path(self) -> None:
        text = _text(NOOPUNK_RUNBOOK)
        self.assertIn("deploy/preflight-noopunk-ai26.sh", text)
        self.assertIn("scripts/ai26-noopunk.sh", text)


class SharedIdentityTests(unittest.TestCase):
    """The two nodes must share identity and differ only in machine class."""

    def test_both_preflights_require_the_same_ai26_identity(self) -> None:
        shared = (
            'LACLAUGPT_VIS_PROJECT_ID:-}" == "ai26"',
            'LACLAUGPT_VIS_BROWSER_DATA_CONTRACT:-}" == "canonical"',
            'LACLAUGPT_VIS_EXECUTION:-}" == "web-service"',
        )
        for fragment in shared:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, _text(LASKIN_PREFLIGHT),
                              "the Laskin preflight no longer checks this; revisit")
                self.assertIn(fragment, _text(NOOPUNK_PREFLIGHT),
                              f"the NooPunk preflight diverged: {fragment}")

    def test_the_machine_class_differs_between_the_nodes(self) -> None:
        """NooPunk is an interactive workstation; Laskin is a server.

        `machine` is a CLASS, not a hostname: the settings model accepts only
        laptop|linux-server|custom. Asserting the class here keeps a later edit
        from inventing a host-specific value the application would reject.
        """
        self.assertIn('LACLAUGPT_VIS_MACHINE:-}" == "laptop"',
                      _text(NOOPUNK_PREFLIGHT))
        self.assertIn('LACLAUGPT_VIS_MACHINE:-}" == "linux-server"',
                      _text(LASKIN_PREFLIGHT))

    def test_noopunk_preflight_refuses_to_claim_the_laskin_class(self) -> None:
        text = _text(NOOPUNK_PREFLIGHT)
        self.assertIn("Laskin uses linux-server", text)

    def test_noopunk_does_not_create_its_own_namespace(self) -> None:
        """A machine never names its own database, bucket or project."""
        text = _text(NOOPUNK_PREFLIGHT)
        for invented in ("noopunk__", "noopunk_laclaugpt", "LACLAUGPT_VIS_MONGODB_DATABASE=noopunk"):
            with self.subTest(invented=invented):
                self.assertNotIn(invented, text)


class CorpusSafetyTests(unittest.TestCase):
    def test_preflight_refuses_a_local_only_corpus_by_default(self) -> None:
        """files-only would show a stale corpus while looking healthy."""
        text = _text(NOOPUNK_PREFLIGHT)
        self.assertIn("would fork the corpus", text)
        self.assertIn("LACLAUGPT_VIS_NOOPUNK_ALLOW_LOCAL_ONLY", text)

    def test_preflight_refuses_analysis_autostart(self) -> None:
        """Starting the UI must not claim shared work away from Laskin."""
        text = _text(NOOPUNK_PREFLIGHT)
        self.assertIn("LACLAUGPT_VIS_ANALYSIS_AUTOSTART", text)
        self.assertIn("read surface", text)

    def test_preflight_refuses_a_wildcard_bind(self) -> None:
        self.assertIn('!= "0.0.0.0"', _text(NOOPUNK_PREFLIGHT))

    def test_runbook_states_the_ui_must_not_start_analysis(self) -> None:
        text = " ".join(_text(NOOPUNK_RUNBOOK).split()).lower()
        self.assertIn("must not start analysis", text)
        self.assertIn("enqueued nothing", text)

    def test_runbook_states_the_shared_store(self) -> None:
        text = " ".join(_text(NOOPUNK_RUNBOOK).split()).lower()
        self.assertIn("must not fork the corpus", text)
        self.assertIn("`ai26` namespace", text)
        self.assertIn("laskin remains the always-on", text)

    def test_runbook_documents_local_ports_and_dependencies(self) -> None:
        text = " ".join(_text(NOOPUNK_RUNBOOK).split()).lower()
        self.assertIn("local ports", text)
        self.assertIn("127.0.0.1:8501", text)
        self.assertIn("dependencies", text)

    def test_runbook_documents_the_three_verbs(self) -> None:
        text = _text(NOOPUNK_RUNBOOK)
        for verb in ("start visualization", "stop  visualization", "status visualization"):
            with self.subTest(verb=verb):
                self.assertIn(verb, text)


class PublicTreePolicyTests(unittest.TestCase):
    """The artifacts must pass the repository's own public-tree policy.

    The repository already has an authoritative credential/private-material scanner
    (scripts/check_public_tree.py) that runs as a required CI check. This delegates
    to it rather than carrying a second, weaker copy of the same rules: a duplicate
    pattern list is how two scanners drift apart, and a credential-shaped literal
    inside the test file itself trips the real scanner -- which is exactly what
    happened to the first version of this test.
    """

    def test_repository_public_tree_policy_accepts_the_tree(self) -> None:
        result = subprocess.run(
            ["python", str(ROOT / "scripts" / "check_public_tree.py")],
            capture_output=True, text=True, cwd=str(ROOT), timeout=120, check=False,
        )
        self.assertEqual(
            result.returncode, 0,
            "the repository public-tree policy rejected the tree:\n"
            + result.stdout + result.stderr,
        )

    def test_noopunk_documents_do_not_hardcode_private_paths(self) -> None:
        """A public runbook must point at the private repository, not carry paths."""
        for path in (NOOPUNK_RUNBOOK, NOOPUNK_WRAPPER):
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                # Assembled from parts so this test file does not itself contain
                # the path-like literals it is checking for: the repository's
                # public-tree scanner flags those on sight, and a test that trips
                # the policy it protects is not a usable test.
                #
                # "/path/to/..." placeholders are deliberately NOT counted. They are
                # the documented stand-in an operator replaces, and the repository's
                # own scanner accepts them; rejecting them here would make the
                # runbook fail its own test for being correctly written.
                for prefix in (
                    "/" + "home" + "/",
                    "/" + "Users" + "/",
                    "/" + "mnt" + "/",
                    "/" + "workspace" + "/",
                ):
                    self.assertNotIn(prefix, text,
                                     f"{path.name} hard-codes {prefix}")


class WrapperContractTests(unittest.TestCase):
    def test_wrapper_never_addresses_the_other_node(self) -> None:
        """NooPunk must not administer Laskin; coordination is contractual."""
        text = _text(NOOPUNK_WRAPPER).lower()
        for forbidden in ("ssh ", "systemctl --host", "laskin"):
            with self.subTest(forbidden=forbidden):
                # 'laskin' may appear only in an explanatory comment
                if forbidden == "laskin":
                    for line in text.splitlines():
                        if "laskin" in line:
                            self.assertTrue(
                                line.lstrip().startswith("#"),
                                f"the wrapper references Laskin outside a comment: {line!r}",
                            )
                else:
                    self.assertNotIn(forbidden, text)

    def test_wrapper_refuses_silent_cloud_analysis(self) -> None:
        text = _text(NOOPUNK_WRAPPER)
        self.assertIn("gemma4:e2b", text)
        self.assertIn("gemma4:31b-cloud", text)
        self.assertIn("cloud is opt-in and never implicit", text)
        self.assertIn("--model must be local or cloud", text)

    def test_wrapper_requires_an_explicit_model_choice(self) -> None:
        """No default that could silently select the cloud model."""
        text = _text(NOOPUNK_WRAPPER)
        # the local model is only the fallback for the explicit `local` branch
        self.assertIn('model="local"', text)

    def test_wrapper_runs_the_preflight_before_starting_the_dashboard(self) -> None:
        self.assertIn("preflight-noopunk-ai26.sh", _text(NOOPUNK_WRAPPER))


if __name__ == "__main__":
    unittest.main()
