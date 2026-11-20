# KingFlow Barber - Deployment Guidemn 

**Production Deployment Documentation**

---

## 🚀 Deployment Options

### Option 1: Docker Compose for Production

The easiest way to deploy the entire stack.

#### Prerequisites
- Docker & Docker Compose installed
- Domain name configured
- SSL certificate (Let's Encrypt recommended)

#### Steps

1. **Clone repository**
```bash
git clone <repository-url>
cd kingflow-barber
```

2. **Configure production environment**
```bash
cp .env.production.example .env
# Edit .env and replace every placeholder with a strong production value.
# URL-encode reserved characters in MYSQL_PASSWORD inside DATABASE_URL.
```

Generate a strong application secret, for example:
```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

3. **Validate and start the production stack**
```bash
docker compose -f docker-compose.prod.yml config --quiet
docker compose -f docker-compose.prod.yml up -d --build
```

Alembic migrations run as part of backend startup. The production Compose file rejects missing database credentials, JWT secret, HTTPS origins and WhatsApp token. Put secrets in the root `.env` file consumed by Compose; never put production credentials in `backend/.env` or an image build context. `.dockerignore` excludes environment files, local uploads, logs, dependency folders and Git metadata from builds. The development `docker-compose.yml` contains local defaults and `DEBUG=True`; do not use it for production.

4. **Create the first platform admin**
```bash
docker compose -f docker-compose.prod.yml exec backend python -m scripts.create_admin
```

Terminate TLS at a trusted HTTPS reverse proxy or managed load balancer, restrict direct access to port 8000 to that proxy, and configure backups for the MySQL volume and `frontend/uploads`. The Compose stack does not configure a TLS proxy or automated backups by itself.

---

### Option 2: VPS Deployment (Manual)

Deploy on a Linux VPS (Ubuntu/Debian recommended).

#### 1. Server Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3.12 python3.12-venv python3-pip mysql-server nginx certbot

# Install Node.js (for frontend)
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs
```

#### 2. Database Setup

```bash
# Create database and restricted application user
sudo mysql
CREATE DATABASE kingflow_barber CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'kingflow'@'localhost' IDENTIFIED BY 'use-a-generated-secret';
GRANT ALL PRIVILEGES ON kingflow_barber.* TO 'kingflow'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

#### 3. Backend Deployment

```bash
# Create app directory
sudo mkdir -p /var/www/kingflow
cd /var/www/kingflow

# Clone repository
git clone <repository-url> .

# Setup virtual environment
python3.12 -m venv venv
source venv/bin/activate

# Install dependencies
cd backend
pip install -r requirements.txt

# Configure environment
cp .env.example .env
nano .env  # Edit with production values

# Run migrations
alembic upgrade head

# Create systemd service
sudo nano /etc/systemd/system/kingflow.service
```

**kingflow.service:**
```ini
[Unit]
Description=KingFlow Barber API
After=network.target

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/var/www/kingflow/backend
Environment="PATH=/var/www/kingflow/venv/bin"
ExecStart=/var/www/kingflow/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

[Install]
WantedBy=multi-user.target
```

```bash
# Start service
sudo systemctl daemon-reload
sudo systemctl start kingflow
sudo systemctl enable kingflow
```

#### 4. Nginx Configuration

```bash
sudo nano /etc/nginx/sites-available/kingflow
```

**Nginx config:**
```nginx
server {
    listen 80;
    server_name api.kingflow.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/kingflow /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

#### 5. SSL Certificate

```bash
# Install Let's Encrypt certificate
sudo certbot --nginx -d api.kingflow.com

# Auto-renewal
sudo systemctl enable certbot.timer
```

---

### Option 3: Cloud Platforms

#### Render preview configuration

The repository's `render.yaml` defines an API preview and a separate notification worker. The API uses a free web service and an externally managed MySQL URL; the worker uses paid compute because it must stay online to drain the outbox. Set the MySQL URL and notification provider credentials for both services. `WHATSAPP_API_URL` must point to a reachable WhatsApp gateway; the manifest does not host that gateway. The API uses Render's `CF-Connecting-IP` header for booking quotas; the service must remain behind Render's edge proxy. Free Render services use an ephemeral filesystem, so uploaded barbershop logos are lost on redeploy or restart; free web services also cannot use persistent disks or send outbound SMTP on ports 465/587. The application stores uploads under `UPLOAD_DIR` (by default, `frontend/uploads`). Before production on Render, use paid API compute with a persistent disk mounted at the configured upload path or integrate durable object storage, and configure an SMTP provider reachable from the paid worker. See [Render persistent disks](https://render.com/docs/disks) and [free service limitations](https://render.com/docs/free).

#### Railway notification worker

Railway's `railway.json` starts the API and runs migrations. Set `CLIENT_IP_HEADER=X-Real-IP` so anonymous booking quotas use Railway's client IP header. Create a second Railway service from the same repository for notifications, set its start command to `cd backend && python -m scripts.notification_worker`, and provide the same MySQL `DATABASE_URL` plus SMTP and WhatsApp gateway variables. Run Alembic migrations only from the API service.

#### AWS Deployment

**Services:**
- **EC2**: Application server
- **RDS**: MySQL database
- **S3**: File storage
- **CloudFront**: CDN
- **Route 53**: DNS

#### DigitalOcean App Platform

```yaml
# app.yaml
name: kingflow-barber
services:
  - name: api
    github:
      repo: <your-repo>
      branch: main
    build_command: pip install -r requirements.txt
    run_command: uvicorn app.main:app --host 0.0.0.0 --port 8000
    envs:
      - key: DATABASE_URL
        value: mysql+pymysql://USER:PASSWORD@MYSQL_HOST:3306/kingflow_barber
        type: SECRET
      - key: SECRET_KEY
        scope: RUN_TIME
        type: SECRET

# Provide a managed MySQL 8 database and store its URL as a secret.
# Set FRONTEND_BASE_URL to the public HTTPS origin (for example, https://kingflow.example)
# so password recovery links use the deployed site rather than localhost.
```

#### Heroku Deployment

```bash
# Install Heroku CLI
curl https://cli-assets.heroku.com/install.sh | sh

# Login
heroku login

# Create app
heroku create kingflow-barber

# Configure DATABASE_URL with a managed MySQL 8 service before deploying.

# Deploy
git push heroku main

# Run migrations
heroku run alembic upgrade head
```

---

## 🔒 Security Checklist

Before going to production:

- [ ] Change `SECRET_KEY` to strong random value
- [ ] Set `DEBUG=False`
- [ ] Use strong database passwords
- [ ] Configure CORS properly (not `*`)
- [ ] Set `SECRET_KEY` to a generated value of at least 32 characters.
- [ ] Set `CORS_ORIGINS` to a JSON list containing only the public HTTPS app origins, such as `["https://app.example.com"]`.
- [ ] Enable HTTPS/SSL
- [ ] Setup firewall rules
- [ ] Enable rate limiting
- [ ] Configure backup strategy
- [ ] Setup monitoring/logging
- [ ] Use environment variables (never hardcode secrets)

---

## 📊 Monitoring

### Application Monitoring

**Recommended tools:**
- **Sentry**: Error tracking
- **Prometheus**: Metrics
- **Grafana**: Dashboards
- **ELK Stack**: Log aggregation

### Health Checks

```bash
# API health
curl https://api.kingflow.com/health

# Database connection
curl https://api.kingflow.com/api/v1/health/db
```

---

## 🔄 CI/CD Pipeline

### GitHub Actions Example

```yaml
# .github/workflows/deploy.yml
name: Deploy to Production

on:
  push:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Run tests
        run: |
          cd backend
          pip install -r requirements.txt
          pytest

      - name: Deploy to server
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SSH_KEY }}
          script: |
            cd /var/www/kingflow
            git pull
            source venv/bin/activate
            pip install -r backend/requirements.txt
            alembic upgrade head
            sudo systemctl restart kingflow
```

---

## 💾 Backup Strategy

### Database Backups

```bash
# Daily backup script
#!/bin/bash
set -euo pipefail
BACKUP_DIR="/backups/kingflow"
MYSQL_CNF="/etc/kingflow/backup.cnf"
DATE="$(date +%Y%m%d_%H%M%S)"
umask 077
mkdir -p "$BACKUP_DIR"
TEMP_BACKUP="$BACKUP_DIR/db_$DATE.sql.gz.tmp"
trap 'rm -f "$TEMP_BACKUP"' EXIT

# backup.cnf must be readable only by the backup account (chmod 600).
# Store its MySQL host, user, password, and port in a [client] section.
mysqldump --defaults-extra-file="$MYSQL_CNF" \
  --single-transaction --routines --triggers --events \
  --databases kingflow_barber | gzip -c > "$TEMP_BACKUP"
gzip -t "$TEMP_BACKUP"
mv "$TEMP_BACKUP" "$BACKUP_DIR/db_$DATE.sql.gz"
trap - EXIT

# Keep only last 30 days
find "$BACKUP_DIR" -type f -name "db_*.sql.gz" -mtime +30 -delete
```

Configure the MySQL backup account with only the privileges required by `mysqldump`; do not put its password on the command line. Back up uploaded logos under `frontend/uploads` as a separate persistent asset set. Periodically restore a backup to an isolated MySQL server and verify application reads before relying on the backup procedure. Never test a restore against the live production database.

### Restore rehearsal

Point the protected client file at a disposable recovery server first. The dump includes `CREATE DATABASE` and `USE` statements for `kingflow_barber`.

```bash
set -euo pipefail
BACKUP_FILE="/backups/kingflow/db_YYYYMMDD_HHMMSS.sql.gz"
MYSQL_CNF="/etc/kingflow/recovery.cnf"
gzip -t "$BACKUP_FILE"
gzip -dc "$BACKUP_FILE" | mysql --defaults-extra-file="$MYSQL_CNF"
```

### Automated Backups

```bash
# Add to crontab
0 2 * * * /usr/local/bin/backup-kingflow.sh
```

---

## 📈 Scaling

### Horizontal Scaling

1. **Add more API servers** behind load balancer
2. **Database read replicas** for read-heavy operations
3. **Notification worker** polls the durable MySQL outbox; the application does not currently use Redis caching.
4. **CDN** for static assets

### Load Balancer (Nginx)

```nginx
upstream api_backend {
    server 10.0.1.10:8000;
    server 10.0.1.11:8000;
    server 10.0.1.12:8000;
}

server {
    location / {
        proxy_pass http://api_backend;
    }
}
```

---

## 🔧 Troubleshooting

### Common Issues

**1. Database connection errors**
```bash
# Check MySQL is running
sudo systemctl status mysql

# Check connection
mysql -u kingflow -p -h localhost kingflow_barber
```

**2. Application won't start**
```bash
# Check logs
sudo journalctl -u kingflow -f

# Check configuration
cd /var/www/kingflow/backend
source ../venv/bin/activate
python -c "from app.core.config import get_settings; print(get_settings())"
```

**3. Nginx errors**
```bash
# Check nginx logs
sudo tail -f /var/log/nginx/error.log

# Test configuration
sudo nginx -t
```

---

## 📞 Support

For deployment assistance:
- Documentation: `/docs`
- Email: support@noventiagroup.com

---

**© 2024 NOVENTIA GROUP - Deployment Guide**
