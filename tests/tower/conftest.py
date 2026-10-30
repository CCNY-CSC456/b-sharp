# tests/conftest.py
import pytest
from src.tower.airport.airport_repo import now

# class Anything:
#     def __eq__(self, other):
#         return True
#
# ANY = Anything()


@pytest.fixture
def runway():
    def _runway(conn, runway_id):
        r_row = conn.execute(
            "SELECT status FROM runways WHERE airport_id = 'JFK' AND runway_id = ?",
            (runway_id,)
        ).fetchone()

        if r_row and r_row[0] == "Not Available":
            return ("Not Available", None, None)

        ra_row = conn.execute(
            "SELECT aircraft_id, assigned_at FROM runway_assignments WHERE airport_id = 'JFK' AND runway_id = ?",
            (runway_id,)
        ).fetchone()

        if ra_row is not None:
            return ("Not Available", ra_row[0], ra_row[1])

        return ("Available", None, now())

    return _runway

