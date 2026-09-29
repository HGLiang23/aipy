# AIPY Web

Next.js App Router frontend for the tenant content workspace. Every page reads and writes
through `lib/api-client.ts`; there is no mock layer.

## Routes

- `/login`: credential sign-in against `POST /api/v1/auth/login`
- `/app`: tenant overview; metrics come from `GET /api/v1/workflow-runs/counts`
- `/app/content`: content runs - search, status filter, pagination, and a create dialog
- `/app/content/[id]`: run detail - generated body, export history, and downloads
- `/app/human-tasks`: review queue; the tabs are server-side filters with real counts
- `/app/materials`: source library - URL import, file upload, filtering, download, and
  attaching a source to a content run
- `/app/admin`: tenant administration navigation; the entries are disabled because the
  corresponding endpoints do not exist yet
- `/forbidden`: shared 403 state

## Local development

```powershell
pnpm install
pnpm dev
```

The client sends session cookies with every request (`credentials: "include"`) and never
puts a tenant ID in a body or a custom header: the server derives tenant context from the
authenticated session. Short-lived access tokens are refreshed once on a `401` and the
original request is replayed.

Set `NEXT_PUBLIC_API_BASE_URL` to point at a non-default API origin; it falls back to
`http://localhost:8000/api/v1`.
