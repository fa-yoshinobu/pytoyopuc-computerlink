# GitHub Release Template: v1.0.3

Use this file as a copy-paste template for the GitHub Releases form.

## Release Settings

- Title: `v1.0.3`
- Tag: `v1.0.3`
- Target: `main`
- Set as latest release: `yes`
- Pre-release: `no`

## Release Body

Documentation and repository-link refresh release.

## Highlights

- updated repository links to `toyopuc-computer-link-python`
- updated GitHub Pages links to the renamed repository path
- added a related repository note for the `.NET` version:
  - `https://github.com/fa-yoshinobu/toyopuc-computer-link-dotnet`
- refreshed generated API docs under `docsrc/api`

## Verification

- `tools\build_api_docs.bat` -> passed
- `python -m build` -> passed
- `python -m twine check dist/*` -> passed

## Included Documents

- `README.md`
- `docsrc/RELEASE.md`
- `docsrc/RELEASE_NOTES.md`
- `docsrc/api/*`

## Assets

- wheel: `dist/toyopuc_computerlink-1.0.3-py3-none-any.whl`
- source tarball: `dist/toyopuc_computerlink-1.0.3.tar.gz`

## Upload Checklist

- attach `toyopuc_computerlink-1.0.3-py3-none-any.whl`
- attach `toyopuc_computerlink-1.0.3.tar.gz`
- confirm the title is `v1.0.3`
- confirm the tag is `v1.0.3`
- confirm release notes match [RELEASE_NOTES.md](RELEASE_NOTES.md)

