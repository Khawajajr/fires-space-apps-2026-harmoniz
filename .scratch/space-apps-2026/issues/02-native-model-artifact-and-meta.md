# 02: Native model artifact + /api/meta

**What to build:** The risk model is stored as LightGBM's native text model plus a metadata JSON instead of a pickle, and the API reports which data and which model it is serving.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Native model text + metadata (features, params, data window, data hash, metrics, git SHA, created_at)
- [ ] One-time loader migrates the old pickle
- [ ] `GET /api/meta`: dataset coverage per sensor, model version, attribution (pydantic model)
- [ ] Contract test for the existing endpoints still green
