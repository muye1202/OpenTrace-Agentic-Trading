# Journal Scripts

This directory contains utility scripts for managing the trading journal daemon.

## Scripts

### `start_journal_daemon.py`
Start the journal scheduler daemon with reflection enabled. This monitors active positions and records outcomes.

**Usage:**
```bash
python scripts/journal/start_journal_daemon.py
```

### `sync_positions_to_journal.py`
Sync existing Alpaca positions into the journal database. Creates theses for positions that were opened before the journal system was activated.

**Usage:**
```bash
python scripts/journal/sync_positions_to_journal.py
```

### `update_trade_dates.py`
Update trade dates in the journal database based on Alpaca order history. Fixes inaccurate trade dates for synced positions.

**Usage:**
```bash
# Dry run (show what would be updated)
python scripts/journal/update_trade_dates.py --dry-run

# Actually update the database
python scripts/journal/update_trade_dates.py
```

### `check_journal.py`
Simple utility to inspect the journal database contents.

**Usage:**
```bash
python scripts/journal/check_journal.py
```

## Requirements

All scripts require:
- Alpaca API credentials in `.env` file
- Journal database at `./journal/trade_journal.db`
- Python packages: `tradingagents`, `alpaca-py`, `python-dotenv`
