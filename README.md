# SHEguru — laptop application, v0.3

Health and safety record management for a South African SME. This first application edition runs on one laptop, opens in a browser and saves data in SQLite. It has no third-party runtime dependencies and no online account is required.

## Start on Windows

1. Extract the complete ZIP into a permanent folder, for example `Documents\SHEguru`. Do not run it from inside the ZIP.
2. Install **Python 3.10 or newer** if needed: https://www.python.org/downloads/windows/ . Choose the option to add Python to PATH if offered.
3. Double-click **Start-SHEguru.bat**. Keep the command window open while using the application. The browser opens at **http://127.0.0.1:8765**.
4. Select **Settings** to add company details, or use **Explore with demo records** on the empty Overview screen to test the workflows first.
5. Stop by pressing **Ctrl+C** in the command window. Start it again whenever needed; saved records remain available.

Visual Studio Code is optional. Opening `web/index.html` directly will not run the application; use the launcher.

On macOS/Linux: `python3 server.py`. Advanced options: `python server.py --no-browser --port 8766 --data-dir /path/to/records`.

## Appointment and company-document checklists (v0.3)

SHEguru targets SMEs with 10 or more employees across industries. This is a product scope, not a universal statutory threshold: duties apply according to the relevant legislation, workplace and hazards. For example, OHS Act section 17 generally uses more than 20 employees at a workplace for health and safety representative designation.

- **Appointments** includes 16 starter role categories; **Documents** includes 18 starter document categories. Each shows a legal / regulatory reference and applicability notes, including conditional construction, machinery and chemical requirements. The source catalogue is `requirements.json`.
- Review each requirement as **Required**, **Not applicable** (with a reason), or leave it as **Review required**. Add company-specific requirements, including separate people, shifts or sites. The starter catalogue is for workplace review, not an exhaustive or independently verified current legal register. Mines, specialist industries, municipal rules and client requirements may need additional items and competent advice.
- Create the appointee in the appointment register, then use **Review / link evidence** on the corresponding requirement to link that appointment. Upload its signed letter directly from the requirement, or link an existing library file. Confirm that the letter names the active appointee. The software records that confirmation; it does not authenticate signatures, qualifications or document contents.
- An applicable appointment stays outstanding until it has an active appointee and linked signed evidence. Changing the appointee requires new confirmation / evidence. Unlinked appointment records also appear as outstanding on the report.
- Company documents stay outstanding until an upload is linked. Optional evidence review / expiry dates and appointment review dates flag overdue items.
- **Reports** includes all requirements, outstanding statuses, assigned people, uploaded filenames, legal references, applicability reasons and notes. Use **Print / save PDF** to export it. Pending applicability decisions are counted separately in the summary and included in the outstanding total. “Evidence recorded” is not a compliance certification.
- Old databases gain the starter checklist without deleting existing records or uploads. Checklists and links are retained in the full SQLite backup. No separate database conversion command is needed.

### Updating a Windows installation safely

1. In the old app, use **Settings → Download full backup**; keep that backup separate.
2. Close the app’s command window and browser tabs.
3. Extract the updated download into a **new folder**, keeping the old installation intact. The new folder must include `requirements.json`, `server.py`, the launchers and the complete `web` directory.
4. To keep existing records, create a `data` folder inside the new folder and copy the backup into it as `sheguru.sqlite3`. Preserve the original backup.
5. Run **Start-SHEguru.bat** in the new folder. Reopen the browser so it loads the new version. Confirm the sidebar says **Laptop edition · 0.3**.

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
node tests/test_requirements.cjs
```

Python and Node tests cover saved-record persistence, employee-departure audit entries, referential and date validation, save conflicts, file round trips, full backup restoration, local access controls, alert logic, text escaping and screen rendering functions. Node is needed for development checks only, not to run the application.

Automated checks passed in Linux. Interactive browser layout, printing and the Windows launcher still require testing on a Windows laptop.

Checklist and evidence flows were also exercised in headless Chromium on Linux, including signed-letter and company-document uploads, report PDF generation, reassignment and reload persistence. Windows interactive printing still needs evaluation on the laptop.

## Development priorities

1. Evaluate these core workflows with the owner and a competent H&S practitioner.
2. Add incidents, corrective actions and risk assessments.
3. Choose the first payroll provider and implement employee status synchronisation.
4. Build course, assessment and certificate verification workflows with appropriate training providers.
5. Design and test multi-company accounts, permissions, cloud storage and deployment before shared use.

The original recovered marketing materials remain preserved separately and have not been overwritten.
