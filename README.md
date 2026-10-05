# Deploy portfolio sites

All deployable build images are stored in GitHub Container Registry (GHCR) as immutable OCI artifacts.
The application repo builds a site per branch, then publishes it as:
`ghcr.io/jensi-bodrya/portfolio-images:<branch-slug>-<sha7>`.

This repo is the **deployment chart**: it stores the environment-to-image reference and controls
which OCI build each environment runs.

```
environments/
  dev.yaml           GHCR image pin for dev
  dev-2.yaml         GHCR image pin for dev-2 (shared test environment)
  prod.yaml          GHCR image pin for production
images/index.json    lightweight provenance catalog (not the image payload)
scripts/
  deploy_oci.py      pull an OCI image from GHCR and deploy its static-site layer
  publish_oci.py     publish a site build as an OCI image
  deploy_env.py      legacy local-directory image deployment helper
  lib.py             shared environment/image registry helpers
.github/workflows/
  deploy.yml         manually deploy a chosen GHCR image to dev/dev-2/prod
  validate.yml       unit tests and manifest validation
```

## Deploy a build

Run **Deploy environment** in GitHub Actions, choose the target environment and enter a ref like:

```text
ghcr.io/jensi-bodrya/portfolio-images:feat-nav-spacing-20e2e6a
```

Feature builds automatically publish immutable images. To test a branch on **dev-2**, use that
branch's image reference. To test main, use the main build's reference. After successful deploy,
the selected GHCR ref is written to `environments/<environment>.yaml`.

## Environments

| Name | Domain | Purpose |
|---|---|---|
| prod | https://jensi-bodrya.surge.sh | Live site |
| dev | https://jensi-bodrya-dev.surge.sh | Dev integration testing |
| dev-2 | https://jensi-bodrya-dev2.surge.sh | Shared feature testing; select any branch image |

The `Deploy environment from GHCR` workflow in this repository pulls the selected image and deploys it to the environment domain. Set GitHub repository secrets `SURGE_LOGIN` and `SURGE_TOKEN` on this repository for deployment. If `portfolio-images` is private, make it public or grant this repository package-read access and configure a GHCR read token.