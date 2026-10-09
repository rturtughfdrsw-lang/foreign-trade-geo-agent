"""Read-only inventory compatibility; no accounts, keys, ACL or clock changes."""
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/inspect_evidence_review_windows.ps1"


@unittest.skipUnless(os.name == "nt", "Windows inventory requires Windows")
class WindowsEvidenceReviewInventoryTests(unittest.TestCase):
    def inventory(self, shell, candidate, *, prefix=""):
        # Source execution leaves the machine's execution policy unchanged.
        # Only this repository's reviewed read-only script is evaluated.
        def literal(value):
            return "'" + str(value).replace("'", "''") + "'"

        command = (
            prefix
            + "& ([scriptblock]::Create([IO.File]::ReadAllText("
            + literal(SCRIPT)
            + "))) -Repository "
            + literal(ROOT)
            + " -CandidateTrustRoot "
            + literal(candidate)
        )
        encoded = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
        result = subprocess.run(
            [shell, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            capture_output=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        return json.loads(result.stdout.decode("utf-8-sig"))

    def assert_inventory(self, data):
        self.assertEqual(data["ProductionGate"], "NO_GO_UNVERIFIED_TRUST_ROOT")
        self.assertEqual(data["Kind"], "READ_ONLY_INVENTORY_NOT_AUTHORIZATION")
        self.assertIsInstance(data["Identity"]["TokenIsAdministrator"], bool)
        self.assertEqual(data["Runtime"]["PersistentKeysCreated"], 0)
        self.assertIs(data["Time"]["TrustedTimeEstablished"], False)
        repository = data["Directories"][0]
        self.assertEqual(repository["State"], "PRESENT")
        self.assertEqual(repository["FileSystem"]["State"], "AVAILABLE")
        self.assertEqual(repository["FileSystem"]["Format"], "NTFS")
        self.assertIn("Rules", repository)

    def test_powershell_51_inventory_does_not_create_missing_trust_root(self):
        shell = shutil.which("powershell.exe")
        if not shell:
            self.skipTest("Windows PowerShell unavailable")
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "missing-trust"
            data = self.inventory(shell, candidate)
            self.assert_inventory(data)
            self.assertEqual(data["Directories"][2]["State"], "MISSING")
            self.assertFalse(candidate.exists())

    def test_powershell_7_reports_existing_candidate_without_changing_it(self):
        shell = shutil.which("pwsh.exe")
        if not shell:
            self.skipTest("PowerShell 7 unavailable")
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory)
            marker = candidate / "marker.txt"
            marker.write_bytes(b"NOT authorization")
            data = self.inventory(shell, candidate)
            self.assert_inventory(data)
            self.assertEqual(data["Directories"][2]["State"], "PRESENT")
            self.assertEqual(marker.read_bytes(), b"NOT authorization")
            self.assertEqual(list(candidate.iterdir()), [marker])

    def test_account_query_failure_is_unknown_and_sanitized(self):
        # An unavailable membership lookup must not label an account restricted.
        prefix = "function Get-LocalUser { throw 'SECRET-CANARY' }; "
        with tempfile.TemporaryDirectory() as directory:
            data = self.inventory(shutil.which("powershell.exe"), directory, prefix=prefix)
            self.assertEqual(data["Identity"]["LocalAccountQueryState"], "UNAVAILABLE")
            self.assertIsNone(data["Identity"]["AccountIsDirectAdministratorMember"])
            self.assertNotIn("SECRET-CANARY", json.dumps(data))
            self.assertEqual(data["ProductionGate"], "NO_GO_UNVERIFIED_TRUST_ROOT")

    def test_non_directory_and_remote_candidates_cannot_appear_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "file"
            candidate.write_bytes(b"NOT authorization")
            shell = shutil.which("powershell.exe")
            data = self.inventory(shell, candidate)
            self.assertEqual(data["Directories"][2]["State"], "NOT_DIRECTORY")
            self.assertEqual(candidate.read_bytes(), b"NOT authorization")
            # Must reject before any UNC lookup; no remote request is attempted.
            data = self.inventory(shell, r"\\invalid.example\trust")
            self.assertEqual(data["Directories"][2]["State"], "NON_LOCAL_PATH_REJECTED")
            self.assertEqual(data["ProductionGate"], "NO_GO_UNVERIFIED_TRUST_ROOT")
