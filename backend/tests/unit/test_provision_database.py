from contextlib import AbstractContextManager

from app.ops import provision_database


class FakeCursor(AbstractContextManager):
    def __init__(self, roles):
        self.roles = roles
        self.commands = []
        self._selected_role = None

    def execute(self, query, parameters=None):
        rendered = str(query)
        self.commands.append((rendered, parameters))
        if rendered.startswith("SELECT 1 FROM pg_roles"):
            self._selected_role = parameters[0]
        elif "CREATE ROLE" in rendered:
            self.roles.add(self._selected_role)

    def fetchone(self):
        return (1,) if self._selected_role in self.roles else None

    def __exit__(self, *args):
        return False


class FakeConnection(AbstractContextManager):
    def __init__(self):
        self.roles = set()
        self.cursors = []

    def cursor(self):
        cursor = FakeCursor(self.roles)
        self.cursors.append(cursor)
        return cursor

    def get_dsn_parameters(self):
        return {"dbname": "cronos_db"}

    def __exit__(self, *args):
        return False


def test_bootstrap_is_repeatable_and_does_not_log_secrets(monkeypatch, capsys):
    connection = FakeConnection()
    monkeypatch.setattr(provision_database.psycopg2, "connect", lambda url: connection)
    environment = {
        "BOOTSTRAP_DATABASE_URL": "postgresql://admin:private@db/cronos_db",
        "CRONOS_MIGRATOR_PASSWORD": "migrator-private",
        "CRONOS_APP_PASSWORD": "app-private",
    }

    provision_database.provision(environment)
    provision_database.provision(environment)

    assert connection.roles == set(provision_database.ROLE_DEFINITIONS)
    output = capsys.readouterr()
    assert "private" not in output.out
    assert "private" not in output.err


def test_main_fails_safely_when_configuration_is_missing(monkeypatch, capsys):
    monkeypatch.delenv("BOOTSTRAP_DATABASE_URL", raising=False)
    monkeypatch.delenv("CRONOS_MIGRATOR_PASSWORD", raising=False)
    monkeypatch.delenv("CRONOS_APP_PASSWORD", raising=False)
    assert provision_database.main() == 1
    assert "BOOTSTRAP_DATABASE_URL" not in capsys.readouterr().err
