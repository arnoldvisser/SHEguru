# SHEguru — laptop application, v0.2

Health and safety record management for a South African SME. This first application edition runs on one laptop, opens in a browser and saves data in SQLite. It has no third-party runtime dependencies and no online account is required.

## Start on Windows

1. Extract the complete ZIP into a permanent folder, for example `Documents\SHEguru`. Do not run it from inside the ZIP.
2. Install **Python 3.10 or newer** if needed: https://www.python.org/downloads/windows/ . Choose the option to add Python to PATH if offered.
3. Double-click **Start-SHEguru.bat**. Keep the command window open while using the application. The browser opens at **http://127.0.0.1:8765**.
4. Select **Settings** to add company details, or use **Explore with demo records** on the empty Overview screen to test the workflows first.
5. Stop by pressing **Ctrl+C** in the command window. Start it again whenever needed; saved records remain available.

Visual Studio Code is optional. Opening `web/index.html` directly will not run the application; use the launcher.

On macOS/Linux: `python3 server.py`. Advanced options: `python server.py --no-browser --port 8766 --data-dir /path/to/records`.

## Working features

- Company name, industry and workplace details.
- Dashboard with appointment gaps, training due within 30 days, overdue reviews and reminders.
- Searchable employee register, optional payroll IDs, edits and departure/reactivation actions.
- Appointment register with employee assignment, review date, legal-basis notes and duties.
- Immediate gap alerts for appointments held by employees marked as having left.
- Training register with providers, due dates and recorded completion dates.
- Reminders with completion/reopening.
- Document uploads/downloads: PDF, JPG/PNG, TXT/CSV, DOCX/XLSX; 10 MB per file.
- Printable appointment letter drafts, using entered company and appointment details.
- Links to official South African legislation sources.
- Change history, including employee departures and the number of appointments affected.
- Full database backup, including records, documents and history.
- Revision checking so stale browser tabs cannot silently overwrite a newer save.

The app begins with an empty database. Demo records are optional and can only be loaded into an empty workspace.

## Backup and restore

Use **Settings → Download full backup** regularly. Keep a copy on a separate drive or a trusted backup service. Backups include employee records and documents; protect them accordingly.

To restore:

1. Stop SHEguru and close its browser tabs.
2. Preserve a copy of the current `data` folder.
3. Copy a SHEguru backup into `data` and name it `sheguru.sqlite3`, replacing the existing database only after preserving that copy.
4. Start SHEguru again.

`data/sheguru.sqlite3` is created on the first launch. It is ignored by Git and excluded from the downloadable source package. It is not encrypted by this app: access depends on the laptop account and disk protections. There is no separate app login or shared-user access in this edition. It listens only on the laptop loopback address.

## Current scope and limits

This is an early single-user working application, ready for evaluation with sample records. It is not a production-ready, multi-company service. There is no payroll-provider connection, background/email notification delivery, course delivery, testing, recognised certificate issuance, automatic legislation monitoring, incident investigation workflow or risk register yet. Payroll IDs are reference fields only.

Appointment and training requirements depend on the workplace. Draft letters require review of legal applicability, competence, duties and signatures. The register does not certify compliance. Uploaded documents are stored as files and are not automatically validated.

## Source structure

- `server.py`: local HTTP service, validation, SQLite persistence, backups and access protections.
- `web/`: browser interface and styles.
- `tests/`: persistence, HTTP and frontend logic tests.
- `Start-SHEguru.bat`: Windows launcher.
- `start.sh`: Unix launcher.

## Validation

Run:

```
python -m unittest discover -s tests -v
node --check web/app.js
node tests/test_frontend.cjs
```

Python and Node tests cover saved-record persistence, employee-departure audit entries, referential and date validation, save conflicts, file round trips, full backup restoration, local access controls, alert logic, text escaping and screen rendering functions. Node is needed for development checks only, not to run the application.

Automated checks passed in Linux. Interactive browser layout, printing and the Windows launcher still require testing on a Windows laptop.

## Development priorities

1. Evaluate these core workflows with the owner and a competent H&S practitioner.
2. Add incidents, corrective actions and risk assessments.
3. Choose the first payroll provider and implement employee status synchronisation.
4. Build course, assessment and certificate verification workflows with appropriate training providers.
5. Design and test multi-company accounts, permissions, cloud storage and deployment before shared use.

The original recovered marketing materials remain preserved separately and have not been overwritten.
