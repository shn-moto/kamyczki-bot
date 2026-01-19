# Serverless Deployment Guide

This guide covers deploying kamyczki-bot to a serverless architecture using:
- **Google Cloud Run** - Bot hosting (webhook mode)
- **Modal.com** - ML inference (CLIP + rembg)
- **Neon.tech** - Serverless PostgreSQL with pgvector

## Architecture

```
[Telegram] → [Cloud Run (webhook)] → [Modal (ML)] → [Neon (PostgreSQL)]
```

## Cost Estimate

| Service | Free Tier | Pay-as-you-go |
|---------|-----------|---------------|
| Cloud Run | 2M requests/month | $0.00001/request |
| Modal | $30/month credits | ~$0.0003/inference |
| Neon | 0.5GB storage | $7/month for 1GB |

**Estimated cost for 70k photos/month: ~$30**

## Prerequisites

1. Google Cloud account with billing enabled
2. Modal.com account
3. Neon.tech account
4. `gcloud` CLI installed
5. `modal` CLI installed

## Step 1: Deploy Modal ML Service

```bash
# Install Modal CLI
pip install modal

# Authenticate
modal token new

# Deploy ML service
modal deploy modal_app.py
```

After deployment, Modal will show the endpoint URL:
```
✓ Created web function process_image_api => https://your-workspace--kamyczki-ml-process-image-api.modal.run
```

Save this URL - you'll need it for the bot configuration.

## Step 2: Set Up Neon Database

1. Create account at https://neon.tech
2. Create new project "kamyczki-bot"
3. Enable pgvector extension:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
4. Copy the connection string (with pooler):
   ```
   postgresql://user:pass@ep-xxx.eu-central-1.aws.neon.tech/kamyczki_bot?sslmode=require
   ```

**Important:** Use the connection string with `-pooler` for serverless compatibility.

## Step 3: Deploy to Cloud Run

### Build and push Docker image

```bash
# Set your project ID
export PROJECT_ID=your-gcp-project

# Build image
docker build -f Dockerfile.cloudrun -t gcr.io/$PROJECT_ID/kamyczki-bot .

# Push to Container Registry
docker push gcr.io/$PROJECT_ID/kamyczki-bot
```

### Deploy to Cloud Run

```bash
gcloud run deploy kamyczki-bot \
  --image gcr.io/$PROJECT_ID/kamyczki-bot \
  --platform managed \
  --region europe-central2 \
  --allow-unauthenticated \
  --set-env-vars "TELEGRAM_BOT_TOKEN=your_token" \
  --set-env-vars "DATABASE_URL=postgresql+asyncpg://user:pass@ep-xxx.aws.neon.tech/kamyczki_bot?sslmode=require" \
  --set-env-vars "MODAL_ENDPOINT_URL=https://your-workspace--kamyczki-ml-process-image-api.modal.run" \
  --set-env-vars "USE_LOCAL_ML=false" \
  --set-env-vars "USE_WEBHOOK=true" \
  --set-env-vars "WEBHOOK_SECRET=your_random_secret" \
  --min-instances 0 \
  --max-instances 10 \
  --memory 256Mi \
  --cpu 1
```

### Set webhook URL

After deployment, Cloud Run will show the service URL. Set it:

```bash
export CLOUD_RUN_URL=https://kamyczki-bot-xxxxx-lm.a.run.app

gcloud run services update kamyczki-bot \
  --set-env-vars "WEBHOOK_URL=$CLOUD_RUN_URL"
```

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather | `123456:ABC...` |
| `DATABASE_URL` | Neon connection string | `postgresql+asyncpg://...` |
| `MODAL_ENDPOINT_URL` | Modal web endpoint | `https://...modal.run` |
| `USE_LOCAL_ML` | Use local ML (false for serverless) | `false` |
| `USE_WEBHOOK` | Use webhook mode | `true` |
| `WEBHOOK_URL` | Cloud Run service URL | `https://...run.app` |
| `WEBHOOK_SECRET` | Random secret for webhook validation | `random_string_123` |
| `WEBAPP_BASE_URL` | Same as WEBHOOK_URL for Mini App | `https://...run.app` |

## Local Development with Serverless Backend

You can test the serverless ML backend locally:

```bash
# .env file
TELEGRAM_BOT_TOKEN=your_token
DATABASE_URL=postgresql+asyncpg://...neon.tech/...
MODAL_ENDPOINT_URL=https://...modal.run
USE_LOCAL_ML=false
USE_WEBHOOK=false  # Use polling for local dev

# Run
python -m src.main
```

## Monitoring

### Cloud Run logs
```bash
gcloud run services logs read kamyczki-bot --limit=100
```

### Modal logs
```bash
modal app logs kamyczki-ml
```

### Neon dashboard
Monitor queries and connections at https://console.neon.tech

## Scaling

Cloud Run automatically scales from 0 to max instances based on traffic.

For high traffic (>100 requests/second):
1. Increase `--max-instances`
2. Consider Modal's `allow_concurrent_inputs` setting
3. Enable Neon connection pooling

## Rollback to Self-Hosted

If you need to go back to self-hosted deployment:

```bash
git checkout release/1.0
docker-compose up -d
```

## Troubleshooting

### Cold start delays
- First request after idle may take 2-5 seconds (Modal warm-up)
- Consider keeping Modal container warm with scheduled pings

### Database connection issues
- Ensure using `-pooler` connection string from Neon
- Check SSL mode is set correctly

### Webhook not receiving updates
- Verify WEBHOOK_URL is correct
- Check WEBHOOK_SECRET matches
- Ensure Cloud Run service allows unauthenticated access
