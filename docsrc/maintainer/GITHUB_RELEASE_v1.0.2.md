# GitHub Release Template: v1.0.2

Use this file as a copy-paste template for the GitHub Releases form.

## Release Settings

- Title: `v1.0.2`
- Tag: `v1.0.2`
- Target: `main`
- Set as latest release: `yes`
- Pre-release: `no`

## Release Body

Regression-guard release for sparse `pc10-word` `read_many` behavior.

## Highlights

- added direct regression test:
  - `test_high_level_read_many_pc10_word_sparse_uses_block_read_only`
- added relay regression test:
  - `test_high_level_relay_read_many_pc10_word_sparse_uses_block_read_only`
- documented the regression guard in `docsrc/TESTING.md`

## Verification

- `python -m pytest tests/_internal/test_relay.py -q` -> `24 passed`
- `python -m pytest -q` -> passed
- `python -m build` -> passed
- `python -m twine check dist/*` -> passed

## Included Documents

- `README.md`
- `docsrc/TESTING.md`
- `docsrc/COMPUTER_LINK_SPEC.md`
- `docsrc/MODEL_RANGES.md`
- `docsrc/RELEASE.md`
- `docsrc/RELEASE_NOTES.md`
- `examples/README.md`
- `tools/README.md`

## Assets

- wheel: `dist/toyopuc_computerlink-1.0.2-py3-none-any.whl`
- source tarball: `dist/toyopuc_computerlink-1.0.2.tar.gz`

## Upload Checklist

- attach `toyopuc_computerlink-1.0.2-py3-none-any.whl`
- attach `toyopuc_computerlink-1.0.2.tar.gz`
- confirm the title is `v1.0.2`
- confirm the tag is `v1.0.2`
- confirm release notes match [RELEASE_NOTES.md](RELEASE_NOTES.md)

