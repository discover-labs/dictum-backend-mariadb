import inspect
import shlex
import subprocess

from dictum_core.backends.secret import Secret

from dictum_backend_mariadb import __version__
from dictum_backend_mariadb.mariadb import MariaDBBackend


def test_version():
    assert __version__ == "0.1.0"


def test_entry_point():
    subprocess.check_call(
        shlex.split(
            "python -c 'from dictum_core.backends.base import Backend; "
            'assert "mariadb" in Backend.registry\''
        )
    )


def test_default_schema():
    assert "default_schema" in MariaDBBackend().parameters


def test_password_is_secret():
    assert (
        inspect.signature(MariaDBBackend.__init__).parameters["password"].annotation
        is Secret
    )
