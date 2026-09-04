#!/bin/bash
# Daily Twitter/X Data Scraping Script
# Runs automatically at 06:00 via cron

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$HERMES_DIR/logs/twitter_scrape_$(date +%Y%m%d).log"

# Create logs directory if it doesn't exist
mkdir -p "$HERMES_DIR/logs"

# Log function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "========================================"
log "Starting daily Twitter/X data scrape"
log "========================================"

# Check rate limiter status
RATE_STATUS=$(python3 /usr/local/bin/rate_limiter.py --status 2>&1)
log "Rate limiter status:"
echo "$RATE_STATUS" | tee -a "$LOG_FILE"

# Check if we have requests remaining
REMAINING=$(echo "$RATE_STATUS" | grep -oP 'Remaining: \K[0-9]+')
if [ -z "$REMAINING" ]; then
    log "ERROR: Could not parse rate limit status"
    exit 1
fi

if [ "$REMAINING" -le 0 ]; then
    log "WARNING: No daily requests remaining. Skipping scrape."
    exit 0
fi

log "Proceeding with scrape ($REMAINING requests available)"

# Run the Twitter scraper
cd "$HERMES_DIR"

# Define priority keywords (high-value searches)
KEYWORDS="hermes,AI agent,LLM,open source AI,chatbot,automation"

# Run scraper with rate limiting
log "Running twitter_scraper.py..."
python3 twitter_scraper.py 2>&1 | tee -a "$LOG_FILE"

SCRAPE_EXIT=$?

if [ $SCRAPE_EXIT -eq 0 ]; then
    log "Scrape completed successfully"
else
    log "WARNING: Scrape completed with exit code $SCRAPE_EXIT"
fi

# Update rate limit status
log "Final rate limit status:"
python3 /usr/local/bin/rate_limiter.py --status 2>&1 | tee -a "$LOG_FILE"

# Check if data was saved
if [ -f "$HERMES_DIR/twitter_data.json" ]; then
    TWEET_COUNT=$(python3 -c "import json; data=json.load(open('$HERMES_DIR/twitter_data.json')); print(len(data))" 2>/dev/null || echo "unknown")
    log "Data saved: twitter_data.json ($TWEET_COUNT tweets)"
else
    log "WARNING: twitter_data.json not created"
fi

log "========================================"
log "Daily scrape complete"
log "========================================"
