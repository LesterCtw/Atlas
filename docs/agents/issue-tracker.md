# Issue Tracker: GitHub

Issues and PRDs for this repo live as GitHub Issues in `LesterCtw/Atlas`.

Use the `gh` CLI for issue operations. When run inside this clone, `gh` can infer the repo from `git remote -v`.

## Conventions

- Create an issue: `gh issue create --title "..." --body "..."`
- Read an issue: `gh issue view <number> --comments`
- List issues: `gh issue list --state open --json number,title,body,labels,comments`
- Comment on an issue: `gh issue comment <number> --body "..."`
- Apply a label: `gh issue edit <number> --add-label "..."`
- Remove a label: `gh issue edit <number> --remove-label "..."`
- Close an issue: `gh issue close <number> --comment "..."`

For multi-line issue bodies, use a heredoc or a temporary markdown file.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.
