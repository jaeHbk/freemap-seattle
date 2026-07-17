# FreeMap Next.js app

This directory contains the production FreeMap Seattle UI and read API.

## Local development

From `web-next/`:

```bash
npm ci
npm run dev
```

Open <http://localhost:3000>. Without Turso variables, local development reads
`../db/deals.db`.

The interactive map uses MapLibre GL with keyless OpenFreeMap vector tiles.
There is no map API key or billing account to configure.

Location discovery recognizes common Seattle neighborhoods locally and uses the
keyless US Census geocoder for street-address searches. Browser geolocation is
used only after the user chooses **Near me**.

## Validation

```bash
npm test
npm run lint
npm run test:e2e
npm run build
```

## Production

Deploy this directory as the Vercel project root. Set
`TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` for Production, Preview, and
Development. See [../docs/DEPLOY.md](../docs/DEPLOY.md).
