# GigaParts Filament Stock

A static stock tracker for GigaParts filament availability.

Live page: <https://bitworks-io.github.io/gigaparts-filament-stock/>

The live page is rebuilt by GitHub Actions once per hour. While open in a
browser, the page also checks `stock-data.json` once per hour for fresh stock
changes.

## Primary Features

- Tracks Bambu Lab and Polymaker filament variants sold by GigaParts.
- Organizes filament by brand tab, material group, and product line.
- Shows in-stock and out-of-stock counts, prices, SKUs, and color swatches.
- Provides Add to Cart links for in-stock variants on hover or keyboard focus.
- Shows newly out-of-stock and newly in-stock alerts at the top of the page.
- Supports browser notifications for newly in-stock variants while the page is
  open.
- Includes search by color name, SKU, material, line, or HEX color. HEX searches
  return the closest available swatch colors across filament types.
- Lets each browser profile keep a saved filament list using `localStorage`,
  with copy, print, and local `mailto:` email actions.

Run:

```sh
python3 build.py
```

The build script downloads the configured GigaParts filament product pages,
parses their embedded Magento variant data, and writes:

- `stock-data.json` - current stock snapshot
- `index.html` - self-contained static tracker
- `manifest.webmanifest` and `sw.js` - installable app and Web Push support

The generated page supports search, stock filtering, sorting, light/dark theme,
variant prices, SKUs, swatch colors, and in-stock hover/focus purchase links.
It also polls `stock-data.json` every hour, shows newly out-of-stock and newly
in-stock changes at the top of the page, and can send browser notifications for
newly in-stock variants while the page is open.

Each browser profile can maintain its own saved filament list using
`localStorage`. The page includes an `Email List` action that opens a local
`mailto:` draft. It does not send email from the site, which keeps the static
GitHub Pages deployment from becoming an email relay.

The generated site files are intentionally ignored on `main`. GitHub Actions
runs `python3 build.py` once per hour, deploys the generated files directly as a
GitHub Pages artifact, and keeps compact stock history on the dedicated
`stock-history` branch. That keeps source-code branches from falling behind due
to hourly stock-only commits while still preserving stock events and trend data.

The `stock-history` branch stores:

- `latest/stock-data.json` - latest full stock snapshot for the next comparison.
- `events/YYYY/MM.ndjson` - compact in-stock and out-of-stock transition events.
- `metrics/hourly/YYYY/MM.csv` - hourly aggregate stock counts.

The deployed site artifact also includes summary data under `history/`, such as
recent events and the last 30 days of hourly counts.

To preview locally:

```sh
python3 build.py
python3 -m http.server 8000
```

Then open `http://localhost:8000`.
