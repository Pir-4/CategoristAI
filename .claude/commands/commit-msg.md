# Generate Commit Message for CategoristAI (--staged: current only | --branch: full branch)

Generate a commit message. Mode is selected via argument or auto-detected.

## Mode Detection

Check `$ARGUMENTS`:
- `--staged` → analyze only current staged/unstaged changes (no questions asked)
- `--branch` → analyze full branch vs main (no questions asked)
- No argument → run `git diff --cached --stat && git diff --stat` to check for staged or unstaged changes:
  - If any changes exist → ASK user: "Current changes detected. Analyze current changes only, or full branch? [staged/branch]"
  - If no changes → use Branch Mode

## Branch Mode Process

1. Get current branch name: `git branch --show-current`
2. Find merge-base with main: `git merge-base HEAD main`
3. Get committed changes on branch: `git diff <merge-base>...HEAD`
4. Get staged changes: `git diff --cached`
5. Get unstaged changes: `git diff`
6. Get untracked files: `git status --porcelain`
7. Get commit history: `git log <merge-base>..HEAD --oneline`
8. Extract Phase number from branch name (see below)
9. If no Phase found, ASK user for it
10. Analyze ALL changes (committed + staged + unstaged + untracked) and generate commit message

## Staged Mode Process

1. Get staged changes: `git diff --cached`
2. Get unstaged changes: `git diff`
3. Get untracked files: `git status --porcelain`
4. Get branch name: `git branch --show-current`
5. Extract Phase number from branch name (see below)
6. If no Phase found → ASK user
7. Analyze ONLY current changes and generate commit message

## Extract Phase from Branch Name

Branch pattern: `phase_{N}/{topic}`

Examples:
- `phase_2/transaction_models` → **Phase 2**, topic `transaction_models`
- `phase_3/ai_agent` → **Phase 3**, topic `ai_agent`
- `main` → no phase prefix

## Commit Message Format

### First Line (Title)
```
[Phase N] <type>: <summary>
```

No phase prefix if on `main` branch:
```
<type>: <summary>
```

**Rules:**
- Max 100 characters
- Summary in imperative mood: "add", "rename", "fix" — not "added", "renamed"
- No trailing punctuation

**Commit types:**
- `feat` — new functionality
- `fix` — bug fix
- `refactor` — code restructure without behavior change
- `test` — adding or fixing tests
- `docs` — documentation only
- `chore` — migrations, dependencies, config

### Body (for complex changes)
- Blank line after first line
- Bullet points: what changed and why
- Mention renamed models/tables if applicable
- Mention new migrations

### Examples

Simple:
```
[Phase 2] feat: add Account model with balance tracking
```

With body:
```
[Phase 2] refactor: rename Expense to Transaction with new classification

- Add TransactionType enum: EXPENSE, INCOME, INTERNAL_TRANSFER, EXTERNAL_TRANSFER
- Add AccountType enum and Account model with match_keyword for CSV parsing
- Add BalanceSnapshot and AccountInterest models
- Rename expenses table to transactions
```

## Output

Output the commit message as plain text (no code blocks, no markdown formatting) so it can be copied directly without leading spaces.

## User hint (optional)

$ARGUMENTS