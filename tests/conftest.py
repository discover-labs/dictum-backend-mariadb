import shlex
import subprocess
import time
from pathlib import Path

import pymysql
import pytest
from dictum_core.tests.conftest import chinook, engine, project  # noqa: F401

from dictum_backend_mariadb.mariadb import MariaDBBackend

container_name = "dictum-mariadb-backend-test"


def stop(fail=False):
    cmd = shlex.split(f"docker stop {container_name}")
    try:
        subprocess.check_call(cmd)
    except subprocess.SubprocessError:
        if fail:
            raise


@pytest.fixture(scope="session")
def backend():
    script = Path(__file__).parent / "chinook.sql"
    cmd = shlex.split(
        f"docker run -d --rm --name {container_name} -p 3306:3306 "
        "-e MYSQL_ROOT_PASSWORD=my-secret-pw -e MYSQL_DATABASE=chinook "
        f"-v {script}:/script.sql "
        "mariadb"  # Using the official MariaDB image
    )
    subprocess.check_call(cmd)
    params = dict(host="localhost", db="chinook", user="root", password="my-secret-pw")
    for _ in range(30):
        try:
            pymysql.connect(**params)
            break
        except pymysql.err.OperationalError:
            time.sleep(1)

    restore_cmd = shlex.split(
        f"docker exec -i {container_name} /bin/bash -c "
        f"'mariadb -u root -pmy-secret-pw chinook < /script.sql'"
    )
    subprocess.check_call(restore_cmd)
    try:
        yield MariaDBBackend(
            database=params["db"],
            host=params["host"],
            username=params["user"],
            password=params["password"],
        )
    finally:
        stop()
