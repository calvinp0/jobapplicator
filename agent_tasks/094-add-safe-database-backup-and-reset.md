# Task 094: Add Safe Database Backup and Reset Tooling

## Goal

Add safe local tooling to back up and reset the JobApplicator development database.

The user wants to reset the database while preserving a backup of the current state.

Do not delete candidate context files.  
Do not delete master resumes.  
Do not delete Gmail tokens unless explicitly requested.  
Do not delete generated run artifacts unless explicitly requested.  
Do not implement Gmail changes in this task.  
Do not change frontend UI in this task.

## Background

The app has accumulated demo/test data and real application data.

The user wants a clean database reset, but with a backup first.

The reset tool should be explicit, safe, and hard to run accidentally.

## Inspect

Inspect:

```text
backend/app/database.py
backend/app/models.py
scripts/
candidate_context/
runs/
.gitignore
README_INSTALL.md
docs/install.md
backend/tests/
```

Search:

```bash
rg "sqlite|database|DB|DATABASE|SessionLocal|engine|seed_demo|reset" backend scripts docs
```

Use the project’s actual database configuration.

## Required Behavior

Add a script for backing up and resetting the local development database.

Suggested script:

```text
scripts/backup_and_reset_db.py
```

The script should:

```text
1. Locate the configured local database.
2. Create a timestamped backup.
3. Reset the active database.
4. Optionally reseed demo data if requested.
5. Print clear next steps.
```

## Safety Requirements

The script must not run destructively without explicit confirmation.

Require one of:

```bash
--confirm-reset
```

or an interactive confirmation prompt.

For non-interactive use:

```bash
python scripts/backup_and_reset_db.py --confirm-reset
```

For dry run:

```bash
python scripts/backup_and_reset_db.py --dry-run
```

The dry run should print:

```text
Database path:
Backup path:
Would reset:
Would preserve:
```

## Backup Location

Store backups under:

```text
backups/database/
```

or another project-standard backup folder.

Example:

```text
backups/database/jobapply_2026-05-26_121530.sqlite3
```

If database is not SQLite, use the appropriate backup/export strategy and document it.

For SQLite, backup by copying the database file after closing connections if possible.

## Reset Scope

Default reset should remove only the application database.

Preserve:

```text
candidate_context/
candidate_context/master_resumes/
candidate_context/evidence_banks/
candidate_context/project_notes/
candidate_context/resume_variants/
candidate_context/gmail/token.json
candidate_context/settings/gmail_oauth.json
runs/
```

Do not delete these by default.

Add optional flags only if useful:

```bash
--delete-runs
--delete-gmail-token
--delete-local-gmail-config
--reseed-demo
```

These must be explicit and documented.

## Reseeding

If the project has:

```text
scripts/seed_demo_data.py
```

support:

```bash
python scripts/backup_and_reset_db.py --confirm-reset --reseed-demo
```

This should reset the DB and then run the seed script or equivalent seed function.

Do not reseed by default unless that is currently project convention.

## Documentation

Update:

```text
README_INSTALL.md
docs/install.md
```

Add section:

```text
Reset local database safely
```

Include commands:

```bash
python scripts/backup_and_reset_db.py --dry-run
python scripts/backup_and_reset_db.py --confirm-reset
python scripts/backup_and_reset_db.py --confirm-reset --reseed-demo
```

Document what is preserved by default.

Document how to restore from backup.

Example restore for SQLite:

```bash
cp backups/database/<backup-file>.sqlite3 <active-db-path>
```

Use actual project paths.

## Tests

Add tests if the project has script tests or if practical.

Tests should prove:

1. Dry run does not delete or modify the DB.
2. Reset requires confirmation.
3. Backup file is created before reset.
4. Candidate context files are preserved.
5. Gmail token/config files are preserved by default.
6. Runs are preserved by default.
7. `--reseed-demo` calls or performs demo seed behavior if implemented.
8. Restore instructions are documented.

If full database reset tests are too invasive, test helper functions using a temporary SQLite database.

## Acceptance Criteria

- There is a documented safe way to back up and reset the local DB.
- Reset requires explicit confirmation.
- Backup is created before destructive reset.
- Candidate context is preserved.
- Gmail token/config are preserved by default.
- Runs are preserved by default.
- Demo reseed is optional.
- Docs explain restore.

## Verification

Run:

```bash
pytest
python scripts/backup_and_reset_db.py --dry-run
```

Manual verification:

1. Run dry run.
2. Confirm it prints DB path and backup path.
3. Run:

```bash
python scripts/backup_and_reset_db.py --confirm-reset
```

4. Confirm backup exists.
5. Confirm app starts with clean DB.
6. Confirm candidate context files still exist.
7. Confirm Gmail token/config were not deleted.
8. Optionally restore from backup and confirm app data returns.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Add safe database backup and reset tooling
```

Do not push.
