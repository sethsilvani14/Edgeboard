# EdgeBoard V3

Mobile-first, sportsbook-agnostic CFB betting research dashboard.

## V3 architecture
EdgeBoard is **not tied to FanDuel, bet365, or any one sportsbook**.

The flow is:

**Market consensus → Model projection → Model edge → Best available price → Estimated EV**

## What V3 does
- Pulls live NCAAF moneyline, spread, and total markets from the US books returned by The Odds API
- Builds consensus spreads/totals using the median available line
- Builds consensus moneyline probabilities using average no-vig probabilities across books
- Measures how tightly or widely books are clustered
- Pulls current-season FBS results + SRS ratings from CollegeFootballData
- Builds a baseline projected score, margin, and total
- Compares the model to the market consensus
- Separately finds the best available line/price for execution
- Explicitly allows PASS instead of forcing a pick

## Required Streamlit secrets
Do **not** commit API keys to this public repo.

In Streamlit Community Cloud: Manage app -> Settings -> Secrets

```toml
ODDS_API_KEY = "your-key"
CFBD_API_KEY = "your-key"
```

## Important caveat
V3 is a baseline research model for plumbing and validation. It has not yet been historically calibrated or proven profitable. Stake labels are experimental until backtesting and out-of-sample validation are implemented.
