# EdgeBoard V3.1 — API-Sports Free Stack

EdgeBoard is a mobile-first Streamlit research dashboard for college-football betting markets.

## What changed in V3.1

The live odds provider is now **API-Sports (American Football / NCAA)** instead of The Odds API.
CollegeFootballData (CFBD) remains the modeling-data source.

Architecture:

**API-Sports market snapshot → market consensus → CFBD model projection → edge → best available price → estimated EV**

## Free-tier design

API-Sports currently provides 100 requests/day on the free American-football API. The NCAA `/odds` endpoint requires a game ID, so EdgeBoard protects the quota by:

- making one NCAA schedule request,
- filtering the schedule to upcoming games whose teams match the CFBD FBS model universe,
- making at most one odds request per eligible game,
- caching that full odds snapshot for 24 hours,
- making the normal **Refresh view** button rerender the app without clearing the API cache.

This prioritizes broad FBS coverage while staying at $0/month. It is intentionally a daily market snapshot, not a live line-movement feed.

## Streamlit Secrets

Do not place keys in this public GitHub repository. Add them in Streamlit Community Cloud under **App settings → Secrets**:

```toml
API_SPORTS_KEY = "your-api-sports-key"
CFBD_API_KEY = "your-cfbd-api-key"
```

## Current model

- CFB pregame only
- moneyline, spread, total
- consensus across bookmakers returned by API-Sports
- current-season CFBD scoring data shrunk toward national average
- CFBD SRS blended with scoring matchup projection
- experimental EV grades and stake labels

This is a research baseline, not a validated profitable betting system. Historical backtesting, probability calibration, closing-line value, persistent records, richer efficiency features, halves, props, live betting, and additional sports are future work.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```
