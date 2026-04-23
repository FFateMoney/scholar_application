# AutoScholar Frontend

Development frontend for the local AutoScholar backend.

## Features

- submit `idea report` jobs
- submit `reference bib` jobs
- show user input snapshot
- show final output preview
- show a development-only debug console for Codex logs

## Files

- `index.html`
- `styles.css`
- `config.js`
- `app.js`

## Run

This frontend is a static site. From the `frontend/` directory:

```bash
python3 -m http.server 4173
```

Then open:

```text
http://127.0.0.1:4173
```

By default it talks to:

```text
http://127.0.0.1:8000
```

Update `config.js` if your backend runs elsewhere.

## Debug Console

The debug console is controlled by `debugMode` in `config.js`.

- `true`: show the Codex debug entry
- `false`: hide developer-facing internal logs
