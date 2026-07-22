# packages/schemas

Shared contract between the API and the web/extension clients. The FastAPI app is
the source of truth; its OpenAPI schema (served at `/openapi.json`) and the
Pydantic models in `apps/api/app/schemas` define the wire format.

To generate TypeScript types for the web app:
```bash
npx openapi-typescript http://localhost:8000/openapi.json -o packages/schemas/api.d.ts
```
Keep generated types out of hand-edits; regenerate on API change.
