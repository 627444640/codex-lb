# Git Workflow & Contribution

1. **Maintainer workflow (2026-09-30)**: Every requested modification in this fork starts on a **fresh `fix/` branch** based on the branch currently being updated. Complete the change and its checks on that fix branch, then merge it back into the starting branch with `--no-ff`. Do not reuse a previous fix branch or edit the target branch directly. This standing instruction authorizes the branch, commits and merge needed for an explicitly requested change. Pushes and PR creation still require authorization in the user's task scope.
2. **Branch Naming**: Use `fix/<short-change-description>-<date>` for each new modification (e.g., `fix/faq-without-llm-20260930`). Record the starting target branch before switching.
3. **Commit Messages**: Follow [Conventional Commits](https://www.conventionalcommits.org/).
   - Format: `<type>(<scope>): <description>`
   - Types: `feat`, `fix`, `docs`, `refactor`, `chore`, `test`
   - Example: `feat(api): add auth endpoint`
4. **PR Titles**: Follow [Conventional Commits](https://www.conventionalcommits.org/) — same format as commit messages.
   - Format: `<type>(<scope>): <description>`
   - Types: `feat`, `fix`, `docs`, `refactor`, `chore`, `test`, `ci`, `perf`, `build`
   - Breaking changes: append `!` before colon — `feat(api)!: remove v1 endpoints`
   - Example: `fix(auth): handle expired refresh token`
5. **Workflow**:

   ```bash
   git switch -c fix/add-login-20260930
   git commit -m "feat(api): add auth endpoint"
   # After validation, switch back to the recorded target and merge:
   git switch <starting-branch>
   git merge --no-ff fix/add-login-20260930
   # Only on explicit request:
   git push origin <starting-branch> fix/add-login-20260930
   gh pr create --title "feat(api): add auth endpoint" --body "..."
   ```

6. **Pushing to Fork PRs**: When a PR comes from a fork (cross-repository), push
   commits directly to the fork's head branch instead of creating a separate PR.

   ```bash
   # 1. Check PR head info
   gh pr view <N> --json headRefName,headRepositoryOwner,isCrossRepository

   # 2. Add fork remote (if not already added)
   git remote add <fork-owner> https://github.com/<fork-owner>/<repo>.git
   git fetch <fork-owner> <head-branch>

   # 3. Checkout fork branch, apply changes, push
   git checkout -b <fork-owner>-<head-branch> <fork-owner>/<head-branch>
   # ... make changes and commit ...
   git push <fork-owner> HEAD:<head-branch>
   ```

   Note: This requires "Allow edits from maintainers" to be enabled on the PR.

7. **Best Practices**: Commit often in small units. Do not commit directly to `main`. Always check `git diff` before pushing.
