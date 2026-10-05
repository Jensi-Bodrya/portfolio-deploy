# Portfolio Deploy — Chart Repo

Stores immutable build images and drives deployments.

This repo is the **single source of truth** for what is deployed where.

```
environments/
  dev.yaml           image pin for the dev environment
  dev-2.yaml         image pin for dev-2 (shared testing)
  prod.yaml          image pin for production
images/
  index.json         registry of all image ids
  <image-id>/        an immutable snapshot of the built site
    site/              deployable payload (index.html, build-meta.json, ...)
    manifest.json      provenance: branch, sha, built_at, registered_at
scripts/
  lib.py             shared helpers (slug, image id, yaml loader, index queries)
  register_image.py  store a built site as a new image
  deploy_env.py      deploy an environment from an image (resolution → deploy → verify)
```

## Registering an image

The application repo's CI runs this after every successful build:

```bash
git clone https://github.com/Jensi-Bodrya/portfolio-deploy
cd portfolio-deploy
python3 scripts/register_image.py \
    --source-dir <path/to/build> \
    --branch <branch> \
    --sha <commit-sha> \
    [--source-repo Jensi-Bodrya/portfolio]
git add images/
git commit -m "image: <image-id>"
git push
```

The image becomes addressable by its id (`<branch-slug>-<sha[:7]>`) and can be
assigned to any environment.

## Deploying

```bash
# deploy whatever dev-2 is pinned to
python3 scripts/deploy_env.py --environment dev-2

# deploy a specific image and pin it
python3 scripts/deploy_env.py --environment dev-2 --image feat-nav-spacing-20e2e6a

# preview without touching Surge
python3 scripts/deploy_env.py --environment dev-2 --dry-run
```

Or use the **Deploy environment** workflow on GitHub Actions (manual dispatch).

## Environments

| Name | Domain | Purpose |
|---|---|---|
| prod | https://jensi-bodrya.surge.sh | Live site |
| dev | https://jensi-bodrya-dev.surge.sh | Auto-deploys on merge to `main` |
| dev-2 | https://jensi-bodrya-dev2.surge.sh | Shared testing — can be pointed at any image |