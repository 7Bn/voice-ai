# gstack

Use the `/browse` skill from gstack for all web browsing. Never use `mcp__claude-in-chrome__*` tools directly.

Available gstack skills:
- `/office-hours` — structured office hours session
- `/plan-ceo-review` — CEO review of a plan
- `/plan-eng-review` — engineering review of a plan
- `/plan-design-review` — design review of a plan
- `/design-consultation` — design consultation session
- `/design-shotgun` — rapid design ideation
- `/design-html` — generate HTML designs
- `/review` — code review
- `/ship` — ship a feature end-to-end
- `/land-and-deploy` — land and deploy changes
- `/canary` — canary deploy workflow
- `/benchmark` — run benchmarks
- `/browse` — web browsing (use this instead of chrome MCP tools)
- `/connect-chrome` — connect to a Chrome instance
- `/qa` — QA workflow
- `/qa-only` — QA only (no fixes)
- `/design-review` — review a design
- `/setup-browser-cookies` — set up browser cookies
- `/setup-deploy` — set up deployment
- `/retro` — retrospective
- `/investigate` — investigate an issue
- `/document-release` — document a release
- `/codex` — codex workflow
- `/cso` — CSO workflow
- `/autoplan` — auto-generate a plan
- `/careful` — careful mode for risky operations
- `/freeze` — freeze a branch
- `/guard` — guard a branch
- `/unfreeze` — unfreeze a branch
- `/gstack-upgrade` — upgrade gstack to latest
- `/learn` — learning workflow

If gstack skills aren't working, run `cd .claude/skills/gstack && ./setup` to build the binary and register skills.

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
