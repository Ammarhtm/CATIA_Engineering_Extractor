# Publish the organized project to the existing GitHub repository

The original ZIP contains a `.git` directory with prior commits. **The GitHub-ready ZIP intentionally omits `.git`**, so it must be merged into your existing working repository rather than uploaded as a new unrelated repository.

## Safe procedure (PowerShell)

1. Make a **local backup** of your current project directory (including `.git` and `output/`); do not delete it.
2. Open PowerShell in your existing checkout (`CATIA_Engineering_Extractor`), and confirm the remote:

   ```powershell
   git remote -v
   git log --oneline -3
   git status --short
   ```

3. Create your new branch, keeping the existing Git history:

   ```powershell
   git switch -c feature/unified-engineering-pipeline
   ```

4. Copy the **contents** of `CATIA_Engineering_Extractor_GitHub_Ready/` into the existing repository (not the parent folder). Overwrite matching source files. **Never overwrite or remove `.git/`**. Keep your working `output/` on your computer for backup/review.
5. Remove any previously tracked generated outputs from Git's index **without deleting local files**:

   ```powershell
   git rm -r --cached --ignore-unmatch output datasets results
   ```

6. Review and stage source files:

   ```powershell
   git add -A
   git status --short
   git diff --cached --stat
   git diff --cached --name-only
   ```

   Check that only source code, tests, scripts, OCR templates, docs and configuration are staged. If something confidential appears, unstage it before proceeding.
7. Verify and commit:

   ```powershell
   python -m pytest -q
   python scripts/check_project.py
   git commit -m "refactor: organize CATIA extraction pipelines and desktop studio"
   git push -u origin feature/unified-engineering-pipeline
   ```

8. In GitHub, create a pull request from the branch into `main`. This presents the changes cleanly to supervisors and preserves the previous history.

> **Security note:** `git rm --cached` removes output data from the **next commit**, but it does not erase data from historical commits. If historical tracked reports are confidential, assess the repository visibility and decide whether its Git history needs a separate scrub *before* publishing it publicly. Do not rewrite history casually, especially if collaborators use it.
