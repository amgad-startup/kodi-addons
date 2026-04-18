# Repository Guidelines

## Project Structure & Module Organization
`default.py` is the Kodi service entry point, `context.py` handles the library context-menu flow, and `reload.py` is a local reload helper. Core logic lives in `resources/lib/`:
`database.py` for SQLite persistence, `metadata.py` for show detection, `chapters.py` for ffmpeg-based chapter parsing, `settings.py` for validated addon settings, and `ui.py` for the skip overlay.

UI and addon metadata live under `resources/skins/default/720p/`, `resources/language/resource.language.en_gb/`, `resources/settings.xml`, and `addon.xml`. Tests are in `test_video_metadata.py` plus the ARM64 harness in `test-container/`. Packaged artifacts belong in `release/`; avoid editing zip outputs by hand.

## Build, Test, and Development Commands
`python3 test_video_metadata.py -v` runs the mocked unit suite without Kodi.

`docker build -t kodi-skipintro-test:arm64 test-container && docker run --rm -v "$(pwd)":/addon kodi-skipintro-test:arm64 test` runs the same checks in the containerized Kodi/ffmpeg environment.

`cd ../repository.skipintro && ./build.sh` builds release zips from the sibling repository used by the release workflow.

## Coding Style & Naming Conventions
Follow the existing Python style: 4-space indentation, `snake_case` for functions and variables, `PascalCase` for classes, and small module-level constants near the top of each file. Keep Kodi log messages prefixed with `SkipIntro:` and use Kodi APIs (`xbmc`, `xbmcgui`, `xbmcvfs`) instead of platform-specific shortcuts where possible.

No formatter or linter is configured in-tree, so match surrounding code and keep imports and control flow simple.

## Testing Guidelines
Add or update `unittest` coverage in `test_video_metadata.py` for behavior changes. Name new tests `test_<behavior>` and keep Kodi dependencies mocked so the suite stays runnable on a normal Python install. Use `test-container/test_chapters_arm.py` only for chapter-parsing checks that need the container harness.

## Commit & Pull Request Guidelines
Recent history follows Conventional Commit style such as `feat: ...`, `fix: ...`, and `fix(scope): ...`; keep subjects imperative and focused. PRs should describe playback impact, settings or schema changes, and manual test coverage. Link the relevant issue when one exists, and include screenshots for changes to `skip_button.xml` or `time_input.xml`.

## Configuration Tips
Do not commit local runtime data such as `special://userdata/.../shows.db`, `__pycache__/`, or ad hoc test media. Treat `release/` artifacts as generated outputs and keep secrets or personal Kodi credentials out of `test-container/kodi-config/`.
