class FakeGeocoder:
    def __init__(self, mapping: dict[str, tuple[float, float]]):
        self.mapping = mapping

    def geocode(self, raw_location: str) -> tuple[float, float] | None:
        return self.mapping.get(raw_location)
