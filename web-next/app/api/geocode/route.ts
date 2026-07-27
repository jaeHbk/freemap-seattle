import {
  parseCensusLocation,
  resolveNeighborhood,
} from "@/lib/location";
import { MARKETS, parseMarket } from "@/lib/markets";

const CENSUS_GEOCODER_URL =
  "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress";

export async function GET(request: Request) {
  const searchParams = new URL(request.url).searchParams;
  const market = parseMarket(searchParams.get("market"));
  const marketConfig = MARKETS[market];
  const query = searchParams.get("q")?.trim() ?? "";
  if (query.length < 2 || query.length > 160) {
    return Response.json(
      {
        error: `Enter a ${marketConfig.label} neighborhood or street address.`,
      },
      { status: 400 },
    );
  }

  const neighborhood = resolveNeighborhood(query, market);
  if (neighborhood) return Response.json(neighborhood);

  const marketName = new RegExp(`\\b${marketConfig.label}\\b`, "i");
  const address = marketName.test(query)
    ? query
    : `${query}, ${marketConfig.addressSuffix}`;
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
    const location = parseCensusLocation(await response.json(), market);
    if (!location) {
      return Response.json(
        {
          error: `No ${marketConfig.label} location matched that search.`,
        },
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
