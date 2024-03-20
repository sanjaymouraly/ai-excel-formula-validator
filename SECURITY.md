# Security and privacy

## Deployment trust model

This release is a **single-user local development/evaluation tool**. It is not a multi-tenant SaaS or a claim that arbitrary hostile Office documents are harmless. Keep API/UI bound to localhost by default. For remote access use TLS, an authentication reverse proxy, `VERIFIER_API_TOKEN`, and `VERIFIER_DASHBOARD_PASSWORD`. API tokens and the simple dashboard password gate do not provide per-user authorization, quotas, session revocation, audit retention or tenant separation. A dashboard visitor with access can use its server-side API permissions; protect the dashboard, not just the API.

Provider profiles are trusted local administrator configuration. Their configurable endpoints can intentionally access local services such as Ollama. Do not expose profile creation to untrusted users; it is not a public SSRF-safe proxy. Outbound requests require explicit opt-in. Connection tests may contact providers for discovery even without generating formulas. No workbook content is attached automatically.

## Workbook boundary

- Only `.xlsx` accepted. Limit 5 MiB upload, 25 MiB total uncompressed ZIP, 300 ZIP members, 20 worksheets, 20,000 used cells.
- Reject unsafe/duplicate ZIP paths, XML DTD/entities, macro parts, external workbook links/relationships, connections, embedded objects and custom UI parts. Validate formulas in every uploaded cell before reserialization.
- Formula text at most 2,000 characters; explicitly allowed functions and bounded A1 ranges only. No VBA, DDE, external formulas, volatile functions, array/data-table formula objects or Python execution.
- Upload IDs and run IDs are generated, not filenames. Artifact downloads use exact per-run allowlists. Reports escape HTML; report CSV neutralizes formula-control prefixes. Raw batch CSV is an intentional formula input, not a safe report.
- The application checks the file after the framework receives it; a reverse proxy **must enforce request-body size, rate, connection and timeout limits** before exposing upload endpoints. ZIP/XML and openpyxl parsing happen in the API process, so parsing itself is not fully isolated. Do not accept adversarial public internet uploads into this local service.
- Store data on a private volume/directory with local filesystem access controls. Reports, fingerprints and changed-cell metadata may reveal business values. No encryption-at-rest is implemented.

## Calculation worker

When supported, bubblewrap launches LibreOffice as the unprivileged invoking user with new user/network/PID namespaces, dropped capabilities, read-only `/usr` and selected runtime files, private `/tmp`, and only the calculation directory writable. Host `/home`, application database, unrelated workbooks and credentials are not mounted. The worker environment is rebuilt without AI keys. The network namespace has no external connectivity.

Inherited resource limits bound per-process CPU (60s), address space (2 GiB), file size (50 MiB) and open files (256). The configured wall-clock timeout kills the Linux process group. These limits are not a cgroup-wide memory/CPU guarantee; in Compose, additional aggregate container memory/CPU/PID controls are configured. Keep the OS and LibreOffice patched. Namespace isolation shares the host kernel and is not equivalent to a hardened VM. Processes running elsewhere as the same local user and trusted administrators are outside the threat model.

If bubblewrap/user namespaces are unavailable, **uploaded workbook execution is refused**. Only locally generated benchmark workbooks over the restricted formula domain can execute in trusted-input mode, with an explicit trust-mode warning. A basic subprocess/tokenizer is not called a full sandbox. Native Windows fallback is for trusted data only; its process-tree cleanup is weaker. Docker files do not enable privileged mode; nested isolation may be unavailable and the app will retain the upload execution gate.

For genuinely hostile workloads, separate the API/file parser and execution service, use per-job hardened containers or microVMs with no network/secrets, filesystem quotas, cgroup limits, and an authenticated queue. That distributed hardened deployment is not implemented or claimed here.

## Credentials, prompts and budgets

Keys exist only in server environment variables or private `.env`; profiles store the variable name, not its value. No key entry form, browser cookies, session tokens or subscription-authentication workaround is used. Provider errors omit raw response bodies and authorization headers. Workbook/report exports do not contain credential configuration values. Environment files and runtime databases are excluded from source control and the release archive.

Users must separately approve sending a prompt to the selected provider. Do not manually paste sensitive workbook data into that prompt unless disclosure is authorized. The application cannot prevent a user from including secrets in manually supplied formulas, prompts or business data; exported evidence retains those inputs, so review before publication.

Cost estimates require supplied prices and reported usage. Reservations intentionally include failed attempts and worst-case retries. Limits apply per local profile and one API process, not an entire provider account or concurrent distributed deployments. Provider billing dashboards remain the source of truth. Do not rely on application reservations as financial authorization controls.

## Retention and upgrades

Run deletion removes its record/workbooks; uploaded source deletion is separate. SQLite does not guarantee forensic erasure of deleted pages, nor do backups. There is no automated retention service. Back up the entire data directory with services stopped. Unknown database schema versions cause startup refusal rather than destructive auto-migration.

## Reporting a vulnerability

Do not publish credentials, private workbooks or exploit-bearing attachments in public issues. Before making a public repository, its owner should configure GitHub private vulnerability reporting and provide a monitored contact. No maintainer security inbox or response SLA has been fabricated for this locally prepared project. If you discover a boundary failure, stop accepting untrusted data, retain redacted reproduction details, and notify the repository owner privately.
