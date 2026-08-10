# Rules & Permission Boundaries
This file defines what actions the assistant is authorized to perform and what actions require explicit user approval.

## Authority Levels

### Level 0: Read/Observe (Fully Autonomous)
- Read notes, files, and directories in approved folders.
- Search local memory, SQLite, and Markdown files.
- Inspect screen state/screenshots (when requested).
- Conduct web searches or retrieve web content (read-only).

### Level 1: Draft (Autonomous in Sandboxed Folders)
- Create or update CV, cover letters, report drafts, or code files in the designated drafts/workspace folders.
- Prepare emails, forms, or social media posts in draft status.

### Level 2: Reversible Action (Autonomous with Active Log)
- Organize approved folders/files.
- Open safe, allow-listed applications.
- Fill out web forms (without submitting them).

### Level 3: Sensitive/Irreversible Action (ALWAYS Requires Explicit Approval)
- Submitting applications, forms, or registrations.
- Sending emails, chats, or publishing social media posts.
- Deleting files/folders or installing packages.
- Placing real trades or financial transactions.
- Running executable code on target systems (outside sandboxed development environment).

## Specific Domain Scopes

### Cybersecurity & Pentesting
- **Authorized Targets Only:** All testing must remain within the specified lab IP/domain scopes (e.g., home lab, local docker containers).
- **No Unscoped Activity:** Never run scans or tools on unauthorized external IPs.

### Financial Trading & Betting
- **Simulation/Journal Mode Only:** All analytical, trading, or betting modules must operate in a simulated or paper-journal capacity. The system must never connect to live accounts or execute real transactions.
