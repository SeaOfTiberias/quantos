# Market Map: screens (spec, 2026-11-04)

How the map reaches the user in the cockpit. Agreed with the user 2026-11-04.

- Mockups: the "Market Map Screens" canvas (claude.ai artifact, private to the user).
- Sprint: `docs/MARKET_MAP_SPRINT_PLAN.md` session S2b, plus the screen items in S6, S7 and S9.
- Look: the cockpit's trading theme (`cockpit/src/trading/theme.js`).

## Rules for every screen

1. **Numbers come from code.** Every value is a `map_read` field (`core/market_map/read.py`) served by the API. Nothing is model output.
2. **Every element carries its test status:** untested (amber), passed (green), or failed its test (grey). Only a passed item may filter or sort a list by default.
3. **Say what isn't built.** Each screen names the layers it shows and the ones still missing, so a short-sighted map can't pass for a complete one.
   - Example: until S5, the 100-day map shows "no strong zone below" where a multi-year base exists. That gap is how the 10-23 HDFCBANK short happened.
4. **Read only.** No screen places, sizes or moves an order. Order release stays `scripts/qorder.py --yes` on the VM.
5. **A screen never runs ahead of its layer.** Each screen is built in the session that builds the data it shows.

## The screens

| # | Screen | Shows | Built in |
|---|---|---|---|
| 1 | Stock map page `#/map/SYMBOL` | Price ladder: strong (and, toggled, weak) zones as bands with their sources; current price; distance in ATR and %; "where price is" summary; the missing-layers banner | S2b |
| 2 | Trade check panel (on screen 1) | Inputs side, entry, stop, target. Outputs 1R, target in R, first obstacle (ROOM), stop placement, flags. From S7 also LOCATION, ALIGNMENT per timeframe, MARKET_BACKDROP | S2b, extended in S7 |
| 3 | Map columns on Picks | LOCATION, ROOM (against the screener's retest plan), MARKET_BACKDROP, each with its status; link to screen 1 | S7 |
| 4 | Map read on Ideas | The frozen read stored with each idea (`map_read` in `trade_ideas.json`), never recomputed | S2b |
| 5 | Market page `#/market` | Index structure and location (Nifty 50, Bank Nifty, Nifty 500, Midcap 150, Smallcap 250, sectors); breadth; sector quadrants; positioning as context. The same content as the pre-market brief | S6 |
| 6 | In-trade card | Open position drawn against its zones; map events (opposing zone, sweep, CHoCH, backdrop flip) as they fire. Alerts only | S9 |

Later layers land on screen 1 as they are built:

- the HTF structure and multi-year zones on the ladder (S5);
- a market-backdrop strip above the ladder (S6);
- a layer-F panel with growth, OPM, ownership trend and the next results date (S6b).

## API (S2b)

| Route | Returns | Notes |
|---|---|---|
| `GET /map/{symbol}` | `map_read(symbol)`, plus the zone list for the ladder | read-only |
| `POST /map/{symbol}/check` | body `{side, entry, stop, target}` → `map_read(symbol, trade)` | read-only, advisory |

- Symbols are validated like `/ideas/structure` (NSE ticker pattern).
- Built 2026-11-04 (`cloud/api/map_routes.py`). `GET` reads at the live Fyers price when it can, else at the map's close, and says which (`price_source`); `/check` reads at the trade's entry and refuses a stop or target on the wrong side. Each ladder zone carries its distance from price (points, ATR, %) from code, and the map's `layers` (shown / missing) feed the banner.
- Weak zones show the same "failed its test" status as strong ones: the 11-04 test ran them as its control and they turned price less often than the strong zones, which did no better than placebo.
- **Trap:** a new API prefix must be added to the VM's nginx allowlist by hand; `deploy-vm.ps1` doesn't sync it.
