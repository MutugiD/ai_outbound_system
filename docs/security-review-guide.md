# Security Review Guide (Internet-facing MVP)

This guide summarizes the security posture and operational verification steps for the internet-facing MVP.

For the full implementation status + detailed security review, see `docs/INTERNET_FACING_MVP_REVIEW.md`.

## Deployment versioning & rollback

This repo deploys **immutable image tags** (SemVer tags like `v0.1.1`).

### Deploy a release
- Create and push a tag on `main` (example):
  - `git tag v0.1.1`
  - `git push origin v0.1.1`
- This triggers `.github/workflows/deploy.yml` to build/push and deploy images tagged `v0.1.1`.

### Rollback
- GitHub Actions → **Deploy** workflow → run manually and set:
  - `image_tag` to an older tag (example: `v0.1.0`)
  - `environment` as needed

### Verify what’s running
- Backend exposes `GET /version` returning:
  - `app_version` (deploy tag when built by workflow)
  - `git_sha`

