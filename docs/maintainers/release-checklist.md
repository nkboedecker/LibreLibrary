# Release checklist

The release workflow arrives with `v0.1.0` preparation. Until then, these steps describe the intended process.

1. Confirm that CI passes on `main`.
2. Complete a manual keyboard and screen-reader pass on the main pages.
3. Open a PR that moves `Unreleased` in `CHANGELOG.md` to the new version and updates the version in `pyproject.toml` and `src/librelibrary/__init__.py`.
4. Merge the PR.
5. Create and push a signed tag, `vX.Y.Z`.
6. Confirm that the release workflow published the image, attestations, signature, release notes, and docs.

For a security rebuild, publish a new patch release. Never overwrite an existing tag.
