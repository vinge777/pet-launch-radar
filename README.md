# Public browser reader

Deployment target: Render, My Workspace. Source branch: pet-catalog-browser. Live status must be checked in Render; a commit alone does not verify deployment.

Deploy this directory as a Docker service (Dockerfile context is this directory). Set `BROWSER_RELAY_TOKEN` to a random secret of at least 32 characters. The service listens on `PORT` (default 10000); health check is `/health`.

After a real deployment, set the Site runtime secrets `BROWSER_RELAY_URL` to its HTTPS origin and `BROWSER_RELAY_TOKEN` to the same secret, then redeploy the Site. Never put either credential in tracked files. The Site will use this browser after direct fetch fails and before optional third-party services.

`POST /scrape` accepts `{ "url": "https://public.example/products/food" }` with Bearer authorization and returns rendered HTML. No user cookies, credentials or private URLs are forwarded. Each request uses a fresh browser context. All HTTP destinations are DNS checked and pinned to public IP addresses, including redirects and subresources. Downloads, WebSockets, service workers, non-GET requests and private query parameters are blocked. Requests and output sizes are bounded.

No automatic captcha solving, authenticated pages or full-web completeness guarantee. The catalog retains failed pages for reconciliation. Dynamic sites that require POST requests or session cookies may not work in this initial reader.

Validation before production acceptance: build Docker image; run network tests; verify `/health`, unauthorized rejection and a real public JavaScript-rendered product page; connect to Site; run a new name-only brand search and reconcile its catalog. Node syntax and address guards alone do not establish browser functionality.
