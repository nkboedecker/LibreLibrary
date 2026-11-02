@AGENTS.md

## Maintainer sessions

These rules apply to Claude Code sessions run by the lead maintainer.

- The maintainer makes all commits and tags. Never commit, push, tag, add remotes, or switch branches.
- Stop at each phase checkpoint. List the changed files and give a suggested commit message and/or PR in Conventional Commits form.
- Make no network writes without explicit approval. This includes accounts, API keys, published images or packages, repositories, releases, tags, settings changes, and triggered workflows.
- Before presenting major code updates as finished, verify all work with the advisor tool if it is available.
- At the end of each phase, run `/code-review` to check all work since the previous review.\
- Ask the maintainer for a real LibraryThing export to use when designing the importer. Keep it out of the repository, in the ignored `private-fixtures/` folder. Any fixture committed to the repository must be anonymized or synthetic.
