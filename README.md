# ai-news-collector

Automated RSS feed collector for AI news articles. Part of the Search-Collect-Process pipeline for AAI-501: Intro to AI and ML at the University of San Diego.

Fetches articles daily from six AI news sources, deduplicates by URL, normalizes metadata, and stores results in a local SQLite database for downstream search and processing.

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

### 4. Run manually to verify

```bash
python collect.py
```

The database will be created at `data/articles.db` on first run.

---

## Scheduling (macOS)

Add the following line to your crontab to run the collector every day at 6 AM:

```bash
crontab -e
```

```
0 6 * * *   /path/to/.venv/bin/python /path/to/collect.py
```

Replace both paths with your actual absolute paths. Confirm the job is registered:

```bash
crontab -l
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

**errors** — feed fetch errors for weekly review

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

-- Errors from the last 7 days (weekly review)
SELECT source, error_msg, occurred_at
FROM errors
WHERE occurred_at >= date('now', '-7 days')
ORDER BY occurred_at DESC;
```

---

## Weekly Review

The pipeline process is reviewed weekly. The review checklist:

- [ ] Query `errors` table for any failed fetches
- [ ] Confirm all six RSS feed URLs return valid responses
- [ ] Check article counts per source for unexpected drops
- [ ] Update `SOURCES` dict in `collect.py` if any feed URLs have changed

---

## Project Structure

```
ai-news-collector/
├── collect.py          # Main pipeline script
├── requirements.txt    # Python dependencies
├── README.md           # This file
└── data/
    └── articles.db     # SQLite database (created on first run; gitignored)
```

---

## Pipeline Architecture

```
Cron trigger (daily 6 AM)
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
Available for search and retrieval
```
