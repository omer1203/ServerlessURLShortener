# GitHub Actions OIDC

Deployment uses `workflow_dispatch` on `main` and a GitHub Environment named `production`. Pull requests do not assume an AWS role.

The trust policy `sub` claim for that job is:

```text
repo:OWNER/ServerlessURLShortener:environment:production
```

Full setup, including the trust policy and a scoped deploy role, is in [docs/DEPLOYMENT.md](../docs/DEPLOYMENT.md).
