# VN Bond Lab - Production Deployment Guide

This guide covers deploying VN Bond Lab on a server (home server, VPS, or bare metal) using Docker Compose and systemd.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start](#quick-start)
3. [Configuration](#configuration)
4. [Security](#security)
5. [HTTPS Setup](#https-setup)
6. [Monitoring](#monitoring)
7. [Backup Strategy](#backup-strategy)
8. [Troubleshooting](#troubleshooting)

## Prerequisites

### System Requirements

- **OS**: Linux (Ubuntu 20.04+, Debian 11+, or similar)
- **RAM**: Minimum 2GB (4GB recommended)
- **Disk**: 20GB+ for data and logs
- **CPU**: 2+ cores

### Software Requirements

```bash
# Docker Engine 20.10+
docker --version

# Docker Compose v2+
docker compose version

# Python 3.10+ (for local development only)
python3 --version
```

### Install Docker and Docker Compose

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add current user to docker group
sudo usermod -aG docker $USER

# Re-login to apply group changes
exit
# (log out and log back in)
```

## Quick Start

### 1. Clone Repository

```bash
# Clone repository
git clone https://github.com/yourusername/vn-bond-lab.git
cd vn-bond-lab
```

### 2. Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit configuration (see Configuration section below)
nano .env
```

### 3. Start Service with Docker Compose

```bash
# Build and start containers
docker compose -f docker-compose.prod.yml up -d

# View logs
docker compose -f docker-compose.prod.yml logs -f
```

### 4. Verify Deployment

```bash
# Health check
curl http://localhost:8000/healthz

# Readiness check
curl http://localhost:8000/readyz

# Metrics (if authentication disabled)
curl http://localhost:8000/metrics
```

### 5. Install as systemd Service (Optional)

```bash
# Copy systemd service file
sudo cp bond-lab.service /etc/systemd/system/

# Update paths in service file if needed
sudo nano /etc/systemd/system/bond-lab.service

# Reload systemd
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable bond-lab.service

# Start service
sudo systemctl start bond-lab.service

# Check status
sudo systemctl status bond-lab.service
```

### 6. Run Tests (Optional)

**Important**: Always run tests using Docker, not the system Python:

```bash
# Run all tests using Docker Compose
docker compose run --rm app pytest -q

# Run with verbose output
docker compose run --rm app pytest -v

# Run specific test file
docker compose run --rm app pytest tests/test_observability.py -v

# Run with coverage
docker compose run --rm app pytest --cov=app --cov-report=html
```

**Common Issue - "python command not found"**:

If you see `python: command not found`, use Docker instead:

```bash
# ❌ DON'T use system Python:
python -m pytest  # This will fail

# ✅ DO use Docker:
docker compose run --rm app pytest -q  # This works
```

Docker includes all dependencies and is the only supported method for running tests.

## Configuration

### Environment Variables

Edit `.env` file to configure the application:

```bash
# Application Settings
APP_NAME=vn-bond-lab
APP_VERSION=1.0.0
DEBUG=false                    # Must be false in production
LOG_LEVEL=INFO                # DEBUG, INFO, WARNING, ERROR

# Server Settings
HOST=0.0.0.0                  # Bind to all interfaces (use 127.0.0.1 for reverse proxy)
PORT=8000

# Database
DB_PATH=/app/data/duckdb/bonds.duckdb

# Observability
LOG_FORMAT=json               # "json" or "text" - JSON recommended for production

# Authentication (See Security section)
ADMIN_AUTH_ENABLED=false      # Enable Basic Auth for /admin/* endpoints
ADMIN_USER=admin
ADMIN_PASSWORD=your_secure_password_here

# Note: BASIC_AUTH_* is deprecated but still supported for backwards compatibility
# The system will automatically map BASIC_AUTH_* to ADMIN_AUTH_* with a warning

# Metrics Authentication
METRICS_AUTH_ENABLED=false    # Require Basic Auth for /metrics endpoint

# Data Collection
START_DATE_DEFAULT=2013-01-01
RATE_LIMIT_SECONDS=1.0
MAX_CONCURRENT_REQUESTS=3
REQUEST_TIMEOUT=30
MAX_RETRIES=3

# Scheduler (Optional - for automated daily ingestion)
SCHEDULER_ENABLED=true
SCHEDULER_DAILY_TIME=18:05    # 6:05 PM
SCHEDULER_TIMEZONE=Asia/Ho_Chi_Minh

# Provider URLs
HNX_BASE_URL=https://hnx.vn
HNX_FTP_BASE_URL=https://owa.hnx.vn/ftp
SBV_BASE_URL=https://www.sbv.gov.vn
ABO_BASE_URL=https://asianbondsonline.adb.org

# Playwright Settings
PLAYWRIGHT_HEADLESS=true
PLAYWRIGHT_TIMEOUT=30000

# Raw Data Storage
RAW_DATA_PATH=/app/data/raw
ENABLE_RAW_STORAGE=true

# Optional External APIs
TRADING_ECONOMICS_API_KEY=     # Leave empty if not using
FRED_API_KEY=                   # Leave empty if not using
```

## Security

### 1. Bind to Localhost Only (Recommended with Reverse Proxy)

If using nginx or Caddy for HTTPS, bind to localhost:

```bash
# In .env
HOST=127.0.0.1
PORT=8000
```

### 2. Enable Admin Authentication

For admin endpoints (`/admin/*`, `/admin/monitoring`, `/admin/quality`, etc.):

```bash
# In .env
ADMIN_AUTH_ENABLED=true
ADMIN_USER=admin
ADMIN_PASSWORD=use_strong_random_password_here
```

Generate a secure password:

```bash
# Generate random password
openssl rand -base64 32
```

**Note**: The old `BASIC_AUTH_*` environment variables are deprecated but still supported. The system will automatically map them to `ADMIN_AUTH_*` with a deprecation warning in the logs.

### 3. Protect Metrics Endpoint

If exposing metrics to monitoring systems (Prometheus, etc.):

```bash
# In .env
METRICS_AUTH_ENABLED=true
ADMIN_AUTH_ENABLED=true
ADMIN_USER=prometheus
ADMIN_PASSWORD=your_prometheus_password
```

### 4. Firewall Configuration

```bash
# Allow HTTP/HTTPS (if exposed directly)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Allow SSH
sudo ufw allow 22/tcp

# Enable firewall
sudo ufw enable

# Check status
sudo ufw status
```

### 5. File Permissions

```bash
# Restrict .env file to owner only
chmod 600 .env

# Restrict data and logs directories
chmod 700 data logs
```

## HTTPS Setup

### Option 1: Using Caddy (Automatic HTTPS)

Caddy automatically obtains and renews Let's Encrypt certificates.

```bash
# Install Caddy
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy

# Configure Caddy
sudo nano /etc/caddy/Caddyfile
```

Caddyfile configuration:

```
your-domain.com {
    reverse_proxy localhost:8000

    # Protect admin endpoints (optional)
    handle /admin/* {
        basicauth {
            admin $2a$14$...  # Use caddy hash-password to generate
        }
        reverse_proxy localhost:8000
    }

    # Protect metrics endpoint
    handle /metrics {
        basicauth {
            prometheus $2a$14$...
        }
        reverse_proxy localhost:8000
    }

    log {
        output file /var/log/caddy/bond-lab-access.log
    }
}
```

Generate password hash for Caddy:

```bash
caddy hash-password --plaintext your_password
```

Restart Caddy:

```bash
sudo systemctl restart caddy
sudo systemctl status caddy
```

### Option 2: Using Nginx + Certbot

```bash
# Install Nginx and Certbot
sudo apt update
sudo apt install nginx certbot python3-certbot-nginx

# Configure Nginx
sudo nano /etc/nginx/sites-available/bond-lab
```

Nginx configuration:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable site and obtain certificate:

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/bond-lab /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx

# Obtain SSL certificate
sudo certbot --nginx -d your-domain.com
```

## Monitoring

### Access Monitoring Dashboard

1. Open browser to `http://your-server:8000/admin/monitoring`
2. If Basic Auth enabled, enter username/password

### What's Monitored

The monitoring dashboard shows:

1. **Pipeline Status**
   - Last ingest run status
   - Last DQ (Data Quality) run status
   - Run durations

2. **SLO Metrics (30 days)**
   - DQ success rate
   - Snapshot coverage
   - Days blocked by errors

3. **Provider Reliability**
   - Success rate per provider
   - Average latency
   - Error counts

4. **Drift Signals**
   - Fingerprint changes (upstream content changes)
   - Parse failures
   - Rowcount regressions

### Prometheus Metrics

If using Prometheus for monitoring:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'bond-lab'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
    basic_auth:
      username: 'prometheus'
      password: 'your_metrics_password'
```

### Health Checks

```bash
# Quick health (no DB check)
curl http://localhost:8000/healthz

# Detailed readiness (includes DB checks)
curl http://localhost:8000/readyz

# Scheduled checks (cron)
*/5 * * * * curl -f http://localhost:8000/healthz || alert
```

## Backup Strategy

### 1. Automated Backup Script

The application includes backup functionality in `app.ops`.

### 2. Setup Cron Job

```bash
# Edit crontab
crontab -e

# Add daily backup at 2 AM
0 2 * * * cd /opt/bond-lab && docker compose -f docker-compose.prod.yml exec -T app python -m app.ops backup

# Add weekly backup on Sunday at 3 AM
0 3 * * 0 cd /opt/bond-lab && docker compose -f docker-compose.prod.yml exec -T app python -m app.ops backup
```

### 3. Setup Systemd Timer (Alternative)

Create `/etc/systemd/system/bond-lab-backup.timer`:

```ini
[Unit]
Description=Daily backup of VN Bond Lab data
Requires=bond-lab.service

[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

Create `/etc/systemd/system/bond-lab-backup.service`:

```ini
[Unit]
Description=Backup VN Bond Lab data
Requires=bond-lab.service

[Service]
Type=oneshot
WorkingDirectory=/opt/bond-lab
ExecStart=/usr/bin/docker compose -f docker-compose.prod.yml exec -T app python -m app.ops backup
```

Enable timer:

```bash
sudo systemctl daemon-reload
sudo systemctl enable bond-lab-backup.timer
sudo systemctl start bond-lab-backup.timer
sudo systemctl list-timers
```

### 4. Backup Location

Backups are stored in:
- Container: `/app/backups/`
- Host: `./backups/` (in project directory)

### 5. Offsite Backup

Copy backups to remote storage:

```bash
# Using rsync to remote server
rsync -avz --delete ./backups/ user@remote-server:/backups/bond-lab/

# Using rclone to cloud storage (S3, GCS, etc.)
rclone sync ./backups/ remote:bucket-name/bond-lab/
```

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker compose -f docker-compose.prod.yml logs

# Check container status
docker ps -a

# Rebuild container
docker compose -f docker-compose.prod.yml up -d --build
```

### Database Errors

```bash
# Check database file exists
ls -lh data/duckdb/bonds.duckdb

# Check disk space
df -h

# Verify database permissions
ls -la data/duckdb/
```

### Scheduler Not Running

```bash
# Check scheduler is enabled in .env
grep SCHEDULER_ENABLED .env

# Verify timezone is correct
grep SCHEDULER_TIMEZONE .env

# Check logs for scheduler errors
docker compose -f docker-compose.prod.yml logs | grep -i scheduler
```

### High Memory Usage

```bash
# Check container resource usage
docker stats

# Adjust memory limits in docker-compose.prod.yml
# Add to service:
# deploy:
#   resources:
#     limits:
#       memory: 2G
```

### Provider Connection Failures

```bash
# Check if provider URLs are accessible
curl -I https://hnx.vn
curl -I https://www.sbv.gov.vn

# Check rate limiting settings
grep RATE_LIMIT_SECONDS .env

# Check for IP blocks
docker compose -f docker-compose.prod.yml logs | grep -i "blocked\|forbidden"
```

### Data Quality Issues

```bash
# Access admin quality dashboard
http://localhost:8000/admin/quality

# Run manual DQ check
docker compose -f docker-compose.prod.yml exec -T app python -m app.quality.run

# Check for drift signals
docker compose -f docker-compose.prod.yml exec -T app python -c "
from app.db.schema import DatabaseManager
from app.config import settings
db = DatabaseManager(settings.db_path)
db.connect()
drifts = db.get_source_fingerprints(limit=20)
for d in drifts:
    print(d)
"
```

### Performance Issues

```bash
# Check database size
du -sh data/duckdb/

# Check raw data size
du -sh data/raw/

# Check logs size
du -sh logs/

# Clean old logs if needed (logs rotate automatically)
# Maximum log file size: 10MB
# Backup count: 5 files
```

### Logs Not Rotating

Logs are configured to rotate automatically:
- Maximum size: 10MB per file
- Backup files: 5

If rotation is not working, check the logging configuration in the application:

```bash
# Check log file sizes
ls -lh logs/

# Manually compress old logs
gzip logs/*.log.1
```

## Updates and Maintenance

### Update Application

```bash
# Pull latest changes
git pull origin main

# Rebuild and restart
docker compose -f docker-compose.prod.yml up -d --build

# Check status
docker compose -f docker-compose.prod.yml ps
```

### Database Maintenance

```bash
# Backup before maintenance
docker compose -f docker-compose.prod.yml exec -T app python -m app.ops backup

# Check database integrity (if needed)
docker compose -f docker-compose.prod.yml exec -T app python -c "
from app.db.schema import DatabaseManager
from app.config import settings
db = DatabaseManager(settings.db_path)
db.connect()
print('Database OK')
db.close()
"
```

### Clean Old Data

```bash
# Remove old backups (> 30 days)
find ./backups -name "*.sql" -mtime +30 -delete

# Remove old logs (> 7 days, if not using automatic rotation)
find ./logs -name "*.log.*" -mtime +7 -delete

# Clean Docker images (reclaim disk space)
docker system prune -a
```

## Support

For issues, questions, or contributions:
- GitHub Issues: https://github.com/yourusername/vn-bond-lab/issues
- Documentation: See `/docs` directory
- Logs: Check `./logs/` directory for detailed logs
