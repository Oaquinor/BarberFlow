# KingFlow Barber - Deployment Guidemn 

**Production Deployment Documentation**

---

## 🚀 Deployment Options

### Option 1: Docker Compose (Recommended for Small/Medium Scale)

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

2. **Configure environment**
```bash
cp backend/.env.example backend/.env
# Edit backend/.env with production values
```

3. **Update docker-compose.yml for production**
```yaml
# Set DEBUG=False
# Use production database credentials
# Configure proper volumes for persistence
```

4. **Start services**
```bash
docker-compose up -d
```

5. **Run migrations**
```bash
docker-compose exec backend alembic upgrade head
```

6. **Create admin user**
```bash
docker-compose exec backend python scripts/create_admin.py
```

---

### Option 2: VPS Deployment (Manual)

Deploy on a Linux VPS (Ubuntu/Debian recommended).

#### 1. Server Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3.12 python3.12-venv python3-pip postgresql nginx certbot

# Install Node.js (for frontend)
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs
```

#### 2. Database Setup

```bash
# Create database and user
sudo -u postgres psql
CREATE DATABASE kingflow_barber;
CREATE USER kingflow WITH PASSWORD 'secure_password_here';
GRANT ALL PRIVILEGES ON DATABASE kingflow_barber TO kingflow;
\q
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

    # WebSocket support
    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
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

#### AWS Deployment

**Services:**
- **EC2**: Application server
- **RDS**: PostgreSQL database
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
        value: ${db.DATABASE_URL}
      - key: SECRET_KEY
        scope: RUN_TIME
        type: SECRET

databases:
  - name: db
    engine: PG
    version: "15"
```

#### Heroku Deployment

```bash
# Install Heroku CLI
curl https://cli-assets.heroku.com/install.sh | sh

# Login
heroku login

# Create app
heroku create kingflow-barber

# Add PostgreSQL
heroku addons:create heroku-postgresql:hobby-dev

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
BACKUP_DIR="/backups/kingflow"
DATE=$(date +%Y%m%d_%H%M%S)

pg_dump -U kingflow kingflow_barber | gzip > $BACKUP_DIR/db_$DATE.sql.gz

# Keep only last 30 days
find $BACKUP_DIR -name "db_*.sql.gz" -mtime +30 -delete
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
3. **Redis cache** for session and frequently accessed data
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
# Check PostgreSQL is running
sudo systemctl status postgresql

# Check connection
psql -U kingflow -d kingflow_barber -h localhost
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
