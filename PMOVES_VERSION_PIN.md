# Pipecat Version Pin — PMOVES.AI

## Current State

| Field | Value |
|-------|-------|
| **Base Release** | `v0.0.102` |
| **Commits Past Tag** | 64 |
| **Current Commit** | `415bb7288` |
| **Branch** | `PMOVES.AI-Edition-Hardened` |
| **Last Upstream Sync** | 2026-02 (merged `pipecat-ai:main`) |

## Pin Rationale

Pipecat is pinned to track the `PMOVES.AI-Edition-Hardened` branch because:

1. **PMOVES-specific modifications** — CLAUDE.md skill hints, custom configuration
2. **Upstream stability** — v0.0.102 is the last tagged release; 64 commits past it include bug fixes and prebuilt updates that we depend on
3. **Flute Gateway dependency** — `pmoves/services/flute-gateway/pipecat/` imports from this submodule

## Update Process

When updating Pipecat:

1. **Check upstream tags**: `git -C PMOVES-Pipecat tag --sort=-v:refname | head -5`
2. **Review changelog**: Check for breaking changes in transport APIs or config formats
3. **Test Flute Gateway**: Ensure voice sessions still work after update
4. **Update this document** with new version info

```bash
# Sync with upstream
cd PMOVES-Pipecat
git fetch pipecat-ai  # or whatever the upstream remote is named
git merge pipecat-ai/main

# Verify
cd ..
curl http://localhost:8055/healthz
```

## Flute Gateway Requirements

The Flute gateway depends on these Pipecat components:

- `pipecat.transports.services.daily` — Daily.co transport
- `pipecat.transports.network.small_webrtc` — WebRTC transport (ESP32 edge future)
- `pipecat.audio` — Audio processing pipeline
- `pipecat.vad` — Voice Activity Detection

Pin exact versions in `pmoves/services/flute-gateway/requirements-pipecat.txt` when deploying.

## Security Considerations

- Pipecat processes audio streams — ensure TLS for all transport channels
- WebRTC STUN/TURN servers should be self-hosted in production
- Audio data in transit is not encrypted by default in local transports
