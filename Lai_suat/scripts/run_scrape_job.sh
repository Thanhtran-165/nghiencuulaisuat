#!/usr/bin/env bash
#
# run_scrape_job.sh
#
# Wrapper script to run bank rate scraping job with proper logging and error handling.
# Designed for use with cron or manual execution.
#
# Usage:
#   ./scripts/run_scrape_job.sh [anomaly_threshold]
#
# Example:
#   ./scripts/run_scrape_job.sh 0.30
#
# Exit codes:
#   0 - Success
#   2 - Anomaly detected (warning, not fatal)
#   3 - Fatal error
#
# Author: Claude Code (Agent)
# Date: 2026-01-05

set -euo pipefail  # Exit on error, undefined variables, pipe failures

# =============================================================================
# Configuration
# =============================================================================

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Default anomaly threshold (30%)
ANOMALY_THRESHOLD="${1:-0.30}"

# Log file with timestamp
LOG_DIR="$PROJECT_ROOT/logs"
LOG_FILE="$LOG_DIR/scrape_$(date +%Y%m%d).log"

# Database path
DB_PATH="$PROJECT_ROOT/data/rates.db"

# Python interpreter
PYTHON_CMD="python3"

# =============================================================================
# Functions
# =============================================================================

log() {
    local level="$1"
    shift
    local message="[$(date '+%Y-%m-%d %H:%M:%S')] [$level] $*"
    echo "$message" | tee -a "$LOG_FILE"
}

create_log_dir() {
    if [ ! -d "$LOG_DIR" ]; then
        mkdir -p "$LOG_DIR"
        log "INFO" "Created log directory: $LOG_DIR"
    fi
}

check_db_exists() {
    if [ ! -f "$DB_PATH" ]; then
        log "ERROR" "Database not found at $DB_PATH"
        log "INFO" "Run 'python3 -m app.cli init-db' first"
        return 1
    fi
}

run_scrape() {
    log "INFO" "Starting scrape job with threshold=$ANOMALY_THRESHOLD"

    cd "$PROJECT_ROOT"

    # Run scrape and capture exit code
    $PYTHON_CMD -m app.cli scrape --all --anomaly-threshold "$ANOMALY_THRESHOLD" 2>&1 | tee -a "$LOG_FILE"
    EXIT_CODE=${PIPESTATUS[0]}

    return $EXIT_CODE
}

interpret_exit_code() {
    local exit_code="$1"

    case $exit_code in
        0)
            log "INFO" "✅ Scrape completed successfully"
            ;;
        2)
            log "WARN" "⚠️  Anomaly detected (record count dropped by >${ANOMALY_THRESHOLD})"
            log "INFO" "Job completed but data may need review"
            ;;
        3)
            log "ERROR" "❌ Fatal error occurred (network failure, parse error, etc.)"
            ;;
        *)
            log "ERROR" "❓ Unknown exit code: $exit_code"
            exit_code=3  # Treat unknown as fatal
            ;;
    esac

    return $exit_code
}

print_summary() {
    local exit_code="$1"

    echo ""
    echo "========================================" | tee -a "$LOG_FILE"
    echo "Scrape Job Summary" | tee -a "$LOG_FILE"
    echo "========================================" | tee -a "$LOG_FILE"
    echo "Timestamp: $(date)" | tee -a "$LOG_FILE"
    echo "Exit Code: $exit_code" | tee -a "$LOG_FILE"
    echo "Log File: $LOG_FILE" | tee -a "$LOG_FILE"
    echo "Database: $DB_PATH" | tee -a "$LOG_FILE"

    # Show database stats if available
    if [ -f "$DB_PATH" ]; then
        local source_count
        source_count=$($PYTHON_CMD -c "from app.db import Database; db = Database('$DB_PATH'); print(len(db.get_all_sources()))" 2>/dev/null || echo "?")
        echo "Sources: $source_count" | tee -a "$LOG_FILE"
    fi

    echo "========================================" | tee -a "$LOG_FILE"
}

# =============================================================================
# Main Execution
# =============================================================================

main() {
    local exit_code

    # Setup
    create_log_dir

    log "INFO" "=========================================="
    log "INFO" "Bank Rate Scraper Job"
    log "INFO" "=========================================="
    log "INFO" "Project: $PROJECT_ROOT"
    log "INFO" "Database: $DB_PATH"
    log "INFO" "Threshold: $ANOMALY_THRESHOLD"

    # Pre-checks
    if ! check_db_exists; then
        exit_code=3
        print_summary $exit_code
        exit $exit_code
    fi

    # Run scrape
    if run_scrape; then
        exit_code=$?
    else
        exit_code=$?
    fi

    # Interpret result
    exit_code=$(interpret_exit_code $exit_code)

    # Print summary
    print_summary $exit_code

    # Exit with proper code
    exit $exit_code
}

# Run main function
main "$@"
