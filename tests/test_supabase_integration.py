"""
Unit tests for Supabase database integration — Backend (Django).

Tasks covered:
  7.1 — DATABASES["default"]["CONN_MAX_AGE"] == 0 and SSL option is set
  7.4 — .env.example contains a Supabase-format DATABASE_URL placeholder
  7.5 — docker-compose.yml has no `postgres` service and no hardcoded DATABASE_URL
  7.7 — docker-compose startup command includes `manage.py migrate`
"""
import os
import sys
import importlib
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

# Paths relative to this file
BACKEND_DIR = Path(__file__).resolve().parents[1]
COMPOSE_FILE = BACKEND_DIR / "docker-compose.yml"


# ---------------------------------------------------------------------------
# 7.1 — Django DATABASES config: CONN_MAX_AGE and SSL
# ---------------------------------------------------------------------------

class TestBackendDatabaseConfig(unittest.TestCase):
    """Verify Django DATABASES["default"] is configured for Supabase/PgBouncer."""

    def _load_settings(self):
        """Import settings with a fake DATABASE_URL injected, bypassing module cache."""
        fake_url = "postgresql://user:pass@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres?sslmode=require"
        env_patch = {
            "DATABASE_URL": fake_url,
            "DJANGO_SECRET_KEY": "test-secret-key-for-unit-tests",
        }
        # Remove cached module so settings are re-evaluated with patched env
        for mod_name in list(sys.modules.keys()):
            if "config.settings" in mod_name or mod_name == "config.settings":
                del sys.modules[mod_name]

        with patch.dict(os.environ, env_patch, clear=False):
            # Ensure the backend package is importable
            if str(BACKEND_DIR) not in sys.path:
                sys.path.insert(0, str(BACKEND_DIR))
            settings = importlib.import_module("config.settings")
        return settings

    def test_conn_max_age_is_zero(self):
        """DATABASES["default"]["CONN_MAX_AGE"] must be 0 for PgBouncer transaction mode."""
        settings = self._load_settings()
        conn_max_age = settings.DATABASES["default"].get("CONN_MAX_AGE")
        self.assertEqual(
            conn_max_age,
            0,
            f"Expected CONN_MAX_AGE=0, got {conn_max_age!r}",
        )

    def test_ssl_option_is_set(self):
        """SSL must be required — either via OPTIONS['sslmode'] or OPTIONS['sslrootcert']."""
        settings = self._load_settings()
        db_default = settings.DATABASES["default"]
        options = db_default.get("OPTIONS", {})
        # dj_database_url with ssl_require=True sets OPTIONS["sslmode"] = "require"
        ssl_mode = options.get("sslmode")
        self.assertEqual(
            ssl_mode,
            "require",
            f"Expected OPTIONS['sslmode']='require', got OPTIONS={options!r}",
        )


# ---------------------------------------------------------------------------
# 7.5 — Backend docker-compose.yml: no postgres service, no hardcoded DATABASE_URL
# ---------------------------------------------------------------------------

class TestBackendDockerCompose(unittest.TestCase):
    """Verify Backend docker-compose.yml does not contain a local postgres service
    or a hardcoded DATABASE_URL value."""

    def _load_compose(self):
        with open(COMPOSE_FILE) as f:
            return yaml.safe_load(f)

    def test_no_postgres_service(self):
        """docker-compose.yml must not define a 'postgres' service."""
        compose = self._load_compose()
        services = compose.get("services", {})
        self.assertNotIn(
            "postgres",
            services,
            "Found a 'postgres' service in docker-compose.yml — it should be removed.",
        )

    def test_no_hardcoded_database_url(self):
        """The backend service environment block must not contain a hardcoded DATABASE_URL."""
        compose = self._load_compose()
        backend_service = compose.get("services", {}).get("backend", {})
        environment = backend_service.get("environment", [])

        # environment can be a list of "KEY=VALUE" strings or a dict
        if isinstance(environment, dict):
            self.assertNotIn(
                "DATABASE_URL",
                environment,
                "Found hardcoded DATABASE_URL in backend environment dict.",
            )
        else:
            for entry in environment:
                self.assertFalse(
                    str(entry).startswith("DATABASE_URL="),
                    f"Found hardcoded DATABASE_URL in backend environment list: {entry!r}",
                )

    def test_env_file_present(self):
        """The backend service must use env_file to supply DATABASE_URL."""
        compose = self._load_compose()
        backend_service = compose.get("services", {}).get("backend", {})
        env_file = backend_service.get("env_file")
        self.assertIsNotNone(
            env_file,
            "Backend service must have an 'env_file' entry to supply DATABASE_URL.",
        )


# ---------------------------------------------------------------------------
# 7.7 — Backend compose startup command includes manage.py migrate
# ---------------------------------------------------------------------------

class TestBackendComposeStartupCommand(unittest.TestCase):
    """Verify the backend container startup command runs migrations before the server."""

    def _load_compose(self):
        with open(COMPOSE_FILE) as f:
            return yaml.safe_load(f)

    def test_startup_command_includes_migrate(self):
        """Backend compose command must include 'manage.py migrate'."""
        compose = self._load_compose()
        backend_service = compose.get("services", {}).get("backend", {})
        command = backend_service.get("command", "")
        self.assertIn(
            "manage.py migrate",
            str(command),
            f"Expected 'manage.py migrate' in startup command, got: {command!r}",
        )


# ---------------------------------------------------------------------------
# 7.4 — Backend .env.example contains Supabase-format DATABASE_URL
# ---------------------------------------------------------------------------

class TestBackendEnvExample(unittest.TestCase):
    """Verify Backend .env.example documents DATABASE_URL in Supabase pooler format."""

    ENV_EXAMPLE = BACKEND_DIR / ".env.example"

    def test_env_example_has_supabase_format(self):
        """Backend .env.example must contain DATABASE_URL pointing to supabase.com."""
        content = self.ENV_EXAMPLE.read_text()
        # Must have a DATABASE_URL line
        self.assertIn(
            "DATABASE_URL=",
            content,
            ".env.example must contain a DATABASE_URL entry.",
        )
        # Must reference supabase.com
        self.assertIn(
            "supabase.com",
            content,
            "DATABASE_URL in .env.example must reference supabase.com.",
        )
        # Must use postgresql:// scheme
        self.assertIn(
            "postgresql://",
            content,
            "DATABASE_URL in .env.example must use postgresql:// scheme.",
        )
        # Must include sslmode=require
        self.assertIn(
            "sslmode=require",
            content,
            "DATABASE_URL in .env.example must include sslmode=require.",
        )


if __name__ == "__main__":
    unittest.main()
