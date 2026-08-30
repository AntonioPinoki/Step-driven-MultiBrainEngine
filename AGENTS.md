# Repository instructions

## Git workflow

- Keep commits focused on one logical change whenever practical.
- Do not push, force-push, rebase published history, or delete branches unless the user explicitly requests it.
- Before committing, inspect the staged diff and avoid including unrelated user changes.
- At the end of work that changes the repository, report:
  - the current branch;
  - the commit hash and commit message, or state clearly that no commit was created;
  - the files changed;
  - the upstream ahead/behind counts when an upstream exists;
  - whether a push was performed.
- Use `tools/git-status.ps1` for the final Git summary. Add `-Fetch` only when current remote information is needed and network access is appropriate.
