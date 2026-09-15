# Architecture and maintenance rules

- Keep POST /api/v1/xray/high-voltage and POST /api/v1/capture; GET /api/v1/files/{filename} downloads saved artifacts.
- api.py owns request adaptation and HTTP responses; adr_client.py owns upstream calls and logging.
- files.py owns fixed-directory output naming; config.py owns deployment settings.
- app.py composes dependencies; __main__.py starts one server process.
- Preserve ADR parameters, HTTP status and response fields; capture adds optional download metadata. No task sessions, database or unrelated endpoints.
- Download only TIFF/DCM/XML files directly inside storage_root; reject directory paths and links.
- Never retry hardware commands automatically or combine capture with voltage control.
- ADR owns acquisition concurrency and AI identification; do not introduce a second evaluation engine.
- Tests inject mock HTTP transports and never operate physical hardware.
