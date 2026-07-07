# Forward paper-trade tracking (P5 — the iron-rule gate)

The iron rule: **no real capital before a live forward run confirms the backtest.**
This is the machinery that produces that forward record.

## What it does

`python main.py forward` runs the *exact* backtest pipeline on freshly fetched
**closed** candles (crypto via OKX, forex via Dukascopy), and records every
newly-resolved paper trade whose zone confirmed **at or after tracking start**
into `forward/forward_log.json`. Because it reuses `simulate_symbol`, forward
results can never drift from backtest logic. The log is committed to git, so it
survives the ephemeral container and accumulates across runs.

- Tracking start was bootstrapped at first run (`meta.tracking_start_ts`).
- Each run adds only setups that confirmed since then and have now resolved.
- `summary()` reports forward expectancy / PF / win-rate to compare against the
  walk-forward reference (**crypto +0.378R, forex +0.237R**). P5 passes when the
  30-day forward expectancy lands within ±0.15R of that.

Run it manually any time:

```bash
python main.py forward                 # both markets
python main.py forward --market crypto # crypto only (fast; OKX)
python main.py forward --bars 800      # candles fetched per stream
```

## Scheduling it (accumulate the record automatically)

The record only grows if `forward` runs periodically. Two options:

### A. Claude Code Routine (fresh session per fire)

Create a daily Routine (via the `create_trigger` tool or the Routines UI) with
`create_new_session_on_fire: true`, cron `0 8 * * *`, and this prompt:

```
Automated SDZ-Sentinel forward tracking run. Work silently, end your turn.
1. cd /home/user/sdz-trading-bot
2. git fetch origin claude/new-session-w46p0y &&
   git checkout claude/new-session-w46p0y &&
   git pull --ff-only origin claude/new-session-w46p0y
3. PYTHONPATH=. python3 main.py forward   (allow ~10 min; forex is slow)
4. If forward/forward_log.json changed: git add it, commit
   "forward: automated tracking update", push to the branch (retry on network err).
5. Otherwise do nothing. Never edit code or open a PR.
```

The committed `.claude/settings.json` SessionStart hook installs Python deps in
the fresh session automatically.

### B. Plain cron on a host that has the repo + deps

```cron
0 8 * * *  cd /path/to/sdz-trading-bot && python3 main.py forward && \
           git add forward/forward_log.json && \
           git commit -m "forward: automated tracking update" && git push
```

## Reading the record

```bash
python -c "import json;d=json.load(open('forward/forward_log.json'));print(len(d['trades']),'resolved')"
```

Once ≥100 resolved trades have accumulated over ~30 days, compare the forward
expectancy to the walk-forward reference. Within ±0.15R → P5 GO.
