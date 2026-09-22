# AIPY Web

Next.js App Router frontend skeleton for the tenant content workspace.

## Routes

- `/login`: static demo login
- `/app`: tenant overview
- `/app/content`: content runs
- `/app/content/[id]`: content run detail placeholder
- `/app/human-tasks`: human review queue
- `/app/materials`: source material library
- `/app/admin`: tenant administration navigation
- `/forbidden`: shared 403 state

## Local development

Dependencies are intentionally not installed in this repository snapshot.

```powershell
pnpm install
pnpm dev
```

The pages currently use `lib/mock-data.ts`. `lib/api-client.ts` defines the FastAPI client boundary. The client does not send a tenant ID in request bodies or custom headers; the server must derive tenant context from the authenticated session.
