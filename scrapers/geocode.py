import time

import httpx

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


class Geocoder:
    def __init__(
        self,
        conn,
        user_agent: str,
        min_interval_seconds: float = 1.0,
        max_live_calls: int = 200,
    ):
        self.conn = conn
        self.user_agent = user_agent
        self.min_interval_seconds = min_interval_seconds
        self.max_live_calls = max_live_calls
        self._live_calls = 0
        self._last_call_at = 0.0

    def geocode(self, raw_location: str) -> tuple[float, float] | None:
        # 1) cache-first
        row = self.conn.execute(
            "SELECT lat, lng, status FROM geocode_cache WHERE raw_location = ?",
            (raw_location,),
        ).fetchone()
        if row is not None:
            if row["status"] == "ok":
                return (row["lat"], row["lng"])
            return None  # cached failure

        # 2) respect the per-run live-call cap
        if self._live_calls >= self.max_live_calls:
            return None

        # 3) polite rate limit between live calls
        if self.min_interval_seconds > 0:
            elapsed = time.monotonic() - self._last_call_at
            if elapsed < self.min_interval_seconds:
                time.sleep(self.min_interval_seconds - elapsed)

        self._live_calls += 1
        self._last_call_at = time.monotonic()
        result = self._live_geocode(raw_location)

        # 4) cache the outcome (success or failure) so we never re-hit it
        if result is not None:
            lat, lng = result
            self.conn.execute(
                "INSERT OR REPLACE INTO geocode_cache(raw_location, lat, lng, status) "
                "VALUES (?,?,?,?)",
                (raw_location, lat, lng, "ok"),
            )
        else:
            self.conn.execute(
                "INSERT OR REPLACE INTO geocode_cache(raw_location, lat, lng, status) "
                "VALUES (?,?,?,?)",
                (raw_location, None, None, "failed"),
            )
        self.conn.commit()
        return result

    def _live_geocode(self, raw_location: str) -> tuple[float, float] | None:
        """Single live Nominatim call. Tests monkeypatch this; never hit in tests."""
        resp = httpx.get(
            NOMINATIM_URL,
            params={"q": raw_location, "format": "json", "limit": 1},
            headers={"User-Agent": self.user_agent},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None
        return (float(data[0]["lat"]), float(data[0]["lon"]))


class FakeGeocoder:
    def __init__(self, mapping: dict[str, tuple[float, float]]):
        self.mapping = mapping

    def geocode(self, raw_location: str) -> tuple[float, float] | None:
        return self.mapping.get(raw_location)
