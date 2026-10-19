import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("scanner", Path(__file__).with_name("check-history-secrets.py"))
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


class HistoryScanTests(unittest.TestCase):
    def test_documentation_and_none_are_not_credentials(self):
        for line in ["Prefixes: sk-proj- sk-ant- ghp_ gho_", "USTC_API=None,", "SESSION_SECRET=${RUNTIME_SECRET}"]:
            self.assertFalse(scanner.suspicious(line, "docs.md"))

    def test_tokens_and_assignments_are_detected(self):
        for line in ["sk-proj-" + "x" * 32, "ghp_" + "a" * 36,
                     "USTC_API=" + "actual-credential-value",
                     'SESSION_SECRET="' + 'actual-session-value"']:
            self.assertTrue(scanner.suspicious(line, "tests/new.py"))

    def test_fixture_exception_is_exact_and_path_scoped(self):
        line = 'USTC_API="' + 'secret-token"'
        self.assertFalse(scanner.suspicious(line, "services/api/tests/test_model_routing.py"))
        self.assertTrue(scanner.suspicious(line, "production.py"))
        self.assertTrue(scanner.suspicious(line.replace("token", "other"), "services/api/tests/test_model_routing.py"))

    def test_new_isolation_fixtures_do_not_exempt_other_files(self):
        fixtures = [
            ("sk-TEST-DOUBLE-" + "shared-provider-key-1234567890",
             "services/api/tests/test_classroom_auth.py"),
            ("sk-TEST-ONLY-" + "provider-key-1234567890", "tests/classroom-login-rate.test.ts"),
        ]
        for value, path in fixtures:
            self.assertFalse(scanner.suspicious(value, path))
            self.assertTrue(scanner.suspicious(value, "production.py"))
            self.assertTrue(scanner.suspicious(value + "-changed", path))


if __name__ == "__main__":
    unittest.main()
