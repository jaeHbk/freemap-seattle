import {
  parseCensusLocation,
  resolveNeighborhood,
} from "@/lib/location";

const CENSUS_GEOCODER_URL =
  "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress";

export async function GET(request: Request) {
  const query = new URL(request.url).searchParams.get("q")?.trim() ?? "";
  if (query.length < 2 || query.length > 160) {
    return Response.json(
      { error: "Enter a Seattle neighborhood or street address." },
      { status: 400 },
    );
  }

  const neighborhood = resolveNeighborhood(query);
  if (neighborhood) return Response.json(neighborhood);

  const address = /\bseattle\b/i.test(query)
    ? query
    : `${query}, Seattle, WA`;
  const params = new URLSearchParams({
    address,
    benchmark: "Public_AR_Current",
    format: "json",
  });

  try {
    const response = await fetch(`${CENSUS_GEOCODER_URL}?${params}`, {
      signal: AbortSignal.timeout(8_000),
      next: { revalidate: 86_400 },
    });
    if (!response.ok) throw new Error(`Census geocoder returned ${response.status}`);
    const location = parseCensusLocation(await response.json());
    if (!location) {
      return Response.json(
        { error: "No Seattle location matched that search." },
        { status: 404 },
      );
    }
    return Response.json(location);
  } catch {
    return Response.json(
      { error: "Location search is temporarily unavailable." },
      { status: 502 },
    );
  }
}
