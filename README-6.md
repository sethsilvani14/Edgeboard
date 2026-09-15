# EdgeBoard V3.2 — Free CFB Stack

Mobile-first Streamlit research dashboard for college-football pregame markets.

## Data stack
- **CollegeFootballData (CFBD):** current-season FBS results and SRS inputs for the baseline model.
- **TheRundown:** current pregame moneyline, spread and total prices. The free tier is delayed and limited to its free-tier sportsbooks.

EdgeBoard is sportsbook-agnostic: it builds a consensus from available books and treats the best available price as a separate execution detail.

## Streamlit Secrets
Add these in Streamlit Community Cloud → App settings → Secrets:

```toml
CFBD_API_KEY = "your-cfbd-key"
THERUNDOWN_API_KEY = "your-rundown-key"
```

Do not commit real API keys to GitHub.

`API_SPORTS_KEY` is no longer used and can be removed from Streamlit Secrets after V3.2 is running.

## Free-tier protection
TheRundown reference catalogs are cached for 24 hours. The seven-day pregame board is cached for 6 hours and requests only full-game moneyline, spread and total markets from the available free-tier books. The app displays provider quota information when supplied in response headers.

## Current scope
CFB only; pregame moneyline, spread and total. No live odds, player props, persistent bet history, or proven profitability yet. Model probabilities and stake labels remain experimental until historical calibration/backtesting is added.
