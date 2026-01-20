# PMOVES.AI Integration Guide for Pipecat Voice Framework

## Integration Complete

The PMOVES.AI integration template has been applied to Pipecat Voice Framework.

## Next Steps

### 1. Customize Environment Variables

Edit the following files with your service-specific values:

- `env.shared` - Base environment configuration
- `env.tier-media` - MEDIA tier specific configuration
- `chit/secrets_manifest_v2.yaml` - Add your service's required secrets

### 2. Update Docker Compose

Add the PMOVES.AI environment anchor to your `docker-compose.yml`:

```yaml
services:
  pipecat-voice:
    <<: [*env-tier-media, *pmoves-healthcheck]
    # Your existing service configuration...
```

### 3. Integrate Health Check

Add the health check endpoint to your service:

```python
from pmoves_health import add_custom_check, get_health_status

@app.get("/healthz")
async def health_check():
    return await get_health_status()
```

### 4. Add Service Announcement

Add NATS service announcement to your startup:

```python
from pmoves_announcer import announce_service

@app.on_event("startup")
async def startup():
    await announce_service(
        slug="pipecat-voice",
        name="Pipecat Voice Framework",
        url=f"http://pipecat-voice:8056",
        port=8056,
        tier="media"
    )
```

### 5. Test Integration

```bash
# Test health check
curl http://localhost:8056/healthz

# Verify environment variables loaded
docker compose exec pipecat-voice env | grep PMOVES

# Verify NATS announcement
nats sub "services.announce.v1"
```

## Service Details

- **Name:** Pipecat Voice Framework
- **Slug:** pipecat-voice
- **Tier:** media
- **Port:** 8056
- **Health Check:** http://localhost:8056/healthz
- **NATS Enabled:** True
- **GPU Enabled:** False

## Files Created

- `env.shared` - Base PMOVES.AI environment
- `env.tier-media` - Tier-specific environment
- `chit/secrets_manifest_v2.yaml` - CHIT secrets configuration
- `pmoves_health/` - Health check module
- `pmoves_announcer/` - NATS service announcer
- `pmoves_registry/` - Service registry client
- `docker-compose.pmoves.yml` - PMOVES.AI YAML anchors

## Support

For questions or issues, see the PMOVES.AI documentation.
