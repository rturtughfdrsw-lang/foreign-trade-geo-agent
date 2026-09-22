from pathlib import Path
import subprocess
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class EnvGitSafetyTests(unittest.TestCase):
    def _git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ("git", *arguments),
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_local_dotenv_names_are_ignored(self) -> None:
        for name in (".env", ".env.local", ".env.development"):
            with self.subTest(name=name):
                result = self._git("check-ignore", "--no-index", "-q", name)
                self.assertEqual(result.returncode, 0)

    def test_dotenv_example_is_tracked_and_not_ignored(self) -> None:
        tracked = self._git("ls-files", "--error-unmatch", ".env.example")
        ignored = self._git(
            "check-ignore",
            "--no-index",
            "-q",
            ".env.example",
        )

        self.assertEqual(tracked.returncode, 0)
        self.assertEqual(ignored.returncode, 1)

    def test_local_dotenv_is_not_tracked(self) -> None:
        result = self._git("ls-files", "--error-unmatch", ".env")

        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
