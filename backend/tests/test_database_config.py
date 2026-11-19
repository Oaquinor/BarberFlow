import pytest

from app.core.database.session import validate_database_url


def test_database_url_accepts_mysql_pymysql():
    url = "mysql+pymysql://kingflow:secret@localhost:3307/kingflow_barber"
    assert validate_database_url(url) == url


@pytest.mark.parametrize("url", [
    "sqlite:///kingflow.db",
    "postgresql://kingflow@localhost/kingflow_barber",
    "mysql://kingflow@localhost/kingflow_barber",
])
def test_database_url_rejects_non_mysql_pymysql_drivers(url):
    with pytest.raises(RuntimeError, match="MySQL PyMySQL"):
        validate_database_url(url)
