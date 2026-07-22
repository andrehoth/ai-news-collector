# ai-news-collector

A lightweight, automated pipeline for collecting and searching AI news articles from curated RSS feeds. Runs daily via launchd, deduplicates by URL, normalizes metadata, and stores results in a local SQLite database. A local Flask web interface provides keyword search and filtering for article review.

This is the **Collect** and **Search** phases of a three-phase Search-Collect-Process pipeline. The Process phase is planned for future development.

---

## Status

| Phase | Status |
|---|---|
| Collect | Complete |
| Search | Complete |
| Process | Planned |

---

## How it works

Six RSS feeds are fetched daily by a launchd job. Each entry is deduplicated by URL hash, normalized to a consistent schema, and inserted into a local SQLite database. Feed errors are logged to a separate table for periodic review. A local Flask web interface provides keyword search, source filtering, and date range filtering over the collected articles.

```
launchd trigger (daily 6 AM, or on next wake if missed)
        |
        v
Fetch via feedparser  <-- SOURCES registry (6 RSS feeds)
        |
        v
Deduplicate  <-- URL hash check against articles table
        |
        v
Normalize  <-- UTC timestamps, UUID assignment, field cleaning
        |
        v
Store to SQLite  --> articles.db
        |
        v
Flask web interface  <-- keyword, source, date range filters
        |
        v
Article selected for review
```

---

## Sources

| Source | Feed |
|---|---|
| IEEE Spectrum AI | `spectrum.ieee.org/feeds/topic/artificial-intelligence.rss` |
| STAT News (Health Tech) | `statnews.com/category/health-tech/feed/` |
| The Decoder | `the-decoder.com/feed/` |
| TechCrunch AI | `techcrunch.com/category/artificial-intelligence/feed/` |
| Ars Technica AI | `arstechnica.com/ai/feed/` |
| VentureBeat AI | `venturebeat.com/category/ai/feed/` |

---

## Sample output

After a typical daily run, the database contains entries across all six sources:

```
('TechCrunch AI',   'Jack Dorsey is taking on Slack with Buzz ...',            '2026-07-21T19:43:41+00:00')
('The Decoder',     'An AI system helped Pakistani judges clear backlogs ...',  '2026-07-21T19:12:20+00:00')
('IEEE Spectrum AI','Why AI Needs a "Genie Coefficient"',                       '2026-07-21T17:41:11+00:00')
('Ars Technica AI', 'Anthropic copyright settlement approved ...',              '2026-07-21T17:33:14+00:00')
('VentureBeat AI',  'The AI agent economy is already here ...',                '2026-07-21T16:45:02+00:00')
('STAT News',       'How AI is reshaping clinical trial design ...',            '2026-07-21T15:22:18+00:00')

Total articles collected: 100+
```

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/<your-username>/ai-news-collector.git
cd ai-news-collector
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. macOS SSL certificates (if using python.org or pyenv Python)

```bash
open /Applications/Python\ 3.x/Install\ Certificates.command
```

Replace `3.x` with your Python version. This is a one-time step.

### 5. Run the collector manually to verify

```bash
python collect.py
```

The database will be created at `data/articles.db` on first run.

### 6. Start the search interface

```bash
python search.py
```

Then open `http://127.0.0.1:5000` in your browser. Press `Ctrl+C` to stop.

---

## Scheduling (macOS — launchd)

The pipeline is scheduled via launchd, which runs the job daily at 6 AM and catches any missed runs on next wake if the machine was asleep.

Create a plist file at `~/Library/LaunchAgents/com.yourusername.ainewscollector.plist` with the following content, substituting your actual paths:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.yourusername.ainewscollector</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/.venv/bin/python3</string>
        <string>/path/to/collect.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>6</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
```

Register the job with launchd:

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.yourusername.ainewscollector.plist
```

Confirm it registered:

```bash
launchctl list | grep ainewscollector
```

Test by triggering manually:

```bash
launchctl kickstart -k gui/$(id -u)/com.yourusername.ainewscollector
```

---

## Database

The SQLite database lives at `data/articles.db` and contains two tables:

**articles** — collected article metadata

| Column | Type | Description |
|---|---|---|
| `id` | TEXT | UUID primary key |
| `source` | TEXT | Source name |
| `title` | TEXT | Article headline |
| `url` | TEXT | Canonical article URL (unique) |
| `url_hash` | TEXT | SHA-256 of URL for deduplication |
| `published_at` | TEXT | ISO 8601 UTC publication timestamp |
| `summary` | TEXT | Feed-provided excerpt |
| `collected_at` | TEXT | ISO 8601 UTC collection timestamp |

**errors** — feed fetch errors for periodic review

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Auto-increment primary key |
| `source` | TEXT | Source that produced the error |
| `error_msg` | TEXT | Error description |
| `occurred_at` | TEXT | ISO 8601 UTC timestamp |

### Useful queries

```sql
-- Articles collected in the last 7 days
SELECT source, title, published_at, url
FROM articles
WHERE published_at >= date('now', '-7 days')
ORDER BY published_at DESC;

-- Count by source
SELECT source, COUNT(*) AS article_count
FROM articles
GROUP BY source
ORDER BY article_count DESC;

-- Errors from the last 7 days
SELECT source, error_msg, occurred_at
FROM errors
WHERE occurred_at >= date('now', '-7 days')
ORDER BY occurred_at DESC;
```

---

## Project structure

```
ai-news-collector/
├── collect.py          # Collect phase -- RSS fetch, dedup, normalize, store
├── search.py           # Search phase -- local Flask web interface
├── templates/
│   └── index.html      # Search UI template
├── requirements.txt    # Python dependencies
├── README.md           # This file
└── data/
    └── articles.db     # SQLite database (created on first run; gitignored)
```
