# Dashboard and PWA Audit — 2026-08-18

## Scope

This audit covers:

- `app/static/index.html`
- `app/static/manifest.json`
- `app/static/service-worker.js`
- FastAPI root/static/OpenAPI behavior
- Dashboard JavaScript endpoint references

The dashboard was audited without exposing the application through a public preview. That is intentional: the current API has unauthenticated host-control and shell-capable routes.

## Validation summary

| Check | Result |
|---|---|
| HTML parser smoke check | Passed |
| Elements parsed after remediation | 380 |
| IDs | 85 unique, no duplicates |
| Buttons after remediation | 39 |
| Form controls | 42 |
| Inline JavaScript syntax (`node --check`) | Passed |
| Literal JavaScript API references | 36 |
| Referenced API routes present | Passed |
| HTML root (`Accept: text/html`) | 200, no-cache headers |
| JSON root (`Accept: application/json`) | 200 |
| `/api/status` | 200 |
| Manifest | 200 |
| Service worker | 200 |
| Swagger UI | 200 |
| OpenAPI | 122 paths / 128 operations |
| Full repository suite after remediation | 260 passed, 3 environment warnings |
| Full browser render | Not completed; Chromium CDN download reset |

## Dashboard areas found

The HTML contains these content panels:

1. Assistant/chat and voice controls
2. Tasks
3. Workspace file editor
4. Specialist tools
5. Browser/desktop automation
6. Screen vision
7. YouTube/web learning
8. Memory vault
9. Models, voice references, and network information
10. Audit logs
11. User manual and policy rules
12. Policy playground

Before remediation, several panels had no navigation button, and the “Mobile & Desktop App” button targeted a nonexistent panel and called a nonexistent JavaScript function. This could leave the dashboard blank after clicking that item.

## Findings

### Critical: remote-use UX conflicts with the security model

The dashboard advertised same-Wi-Fi mobile access while the API had no authentication. The same API includes direct routes for OS input, filesystem mutation, host command execution, dynamic code, Android control, and shutdown.

**Remediation in this pass:** replace the invitation with a warning that remote mode is disabled/unsafe until authenticated remote access is implemented. The README now instructs loopback binding only.

### High: service worker cached private API GET responses

The previous network-first handler cached every successful GET request, not only application shell assets. That could include memory, audit logs, user rules, system information, or future authenticated content.

**Remediation in this pass:** cache only same-origin navigation requests and `/static/` assets. API and cross-origin requests always use the network path and are not written to Cache Storage.

### High: navigation contract was broken

- `switchTab('mobile-app')` had no `#tab-mobile-app` element.
- It attempted to call `loadNetworkInfo()`, but the implemented function is `fetchNetworkInfo()`.
- Specialist, automation, vision, learner, and policy-playground panels were unreachable from navigation.
- `switchTab` depended on the browser-specific global `event` object.

**Remediation in this pass:** make every panel reachable, point the mobile/models button at the existing models panel, pass `this` explicitly, and accept a trigger button argument rather than reading global `event`.

### Medium: PWA icons were declared but absent

The manifest referenced `/static/icon-192.png` and `/static/icon-512.png`, but neither file existed. This breaks install metadata and causes 404s.

**Remediation in this pass:** add both local PNG icons.

### Medium: form controls lacked programmatic names

Most visual labels had no `for` relationship, and several selectors/input fields had only adjacent text spans. Automated inspection found 40 ID-bearing controls without a programmatic label.

**Remediation in this pass:** add `aria-label` names to ID-bearing controls. A later component rewrite should use explicit `<label for="…">` relationships wherever possible.

### Medium: voice cloning copy exceeded implementation

The UI called its feature a custom voice cloner. The backend stores WAV reference profiles but synthesizes with `pyttsx3`; the reference audio does not change the synthesized voice.

**Remediation in this pass:** relabel the panel as experimental voice reference profiles and state that timbre cloning is not implemented by the current backend.

### Low/medium: external font dependency

The dashboard loaded Google Fonts despite being described as local/offline. This creates a network dependency and discloses a request to a third party.

**Remediation in this pass:** remove the external stylesheet. Existing CSS falls back to system sans-serif and monospace fonts.

### Maintainability: monolithic static application

At audit time:

- `index.html`: about 119 KB
- Inline JavaScript: about 66 KB
- API calls, presentation, state, media handling, and feature logic share one file

This structure is workable for a prototype but makes security review, component testing, cache policy, and accessibility regression control harder.

**Recommended next step:** split the dashboard into versioned local CSS/JS modules before adding more panels. A framework is optional; modular vanilla JavaScript would already improve maintainability.

### Error handling and truthful status need a later pass

Many UI actions read JSON without consistently checking `res.ok`. Some backend integrations return fallback “success” values even when the real operation was not performed. Browser-level UX tests should be added after those backend contracts are corrected.

## Remediation contract added by this pass

Static tests now check that:

- Every dashboard tab has a navigation target.
- Every navigation target has a corresponding panel.
- ID-bearing controls have an accessible name.
- Manifest icon files exist.
- The service worker restricts caching to the application shell/static assets.
- The dashboard includes the unauthenticated-remote-access warning.

## Remaining browser test plan

The browser binary could not be downloaded in this environment because the Playwright CDN connection reset. On a development machine with Chromium installed, run:

```bash
python -m playwright install chromium
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then validate at desktop and mobile viewports:

1. No console errors during initial load.
2. Every navigation tab displays a nonempty panel.
3. Simple/expert mode does not strand the user on a hidden panel.
4. Keyboard focus is visible and ordered.
5. Chat handles offline LM Studio without losing the user message.
6. All forms render backend errors without claiming success.
7. Microphone/camera/GPS permission denial is handled clearly.
8. Service worker stores only `/` and `/static/*`, never API JSON.
9. Installability passes browser PWA checks.
10. Destructive actions require authenticated approval before the UI enables them.

## Security note

A live preview was intentionally not started. Do not treat “local network” as an authorization boundary. Complete authenticated remote mode and route-level policy enforcement before restoring mobile LAN instructions.
