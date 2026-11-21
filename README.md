# email-agent

An email agent built on a home-built harness: agent loop, tools, hooks, memory, context engineering, and evals. No agent framework.

> **Status:** early. Milestone 0 (foundations) is in progress. The design spec is [issue #3](https://github.com/canyon-velvet/email-agent/issues/3).

## Requirements

- [uv](https://docs.astral.sh/uv/), which installs Python 3.12 if you don't have it

## Setup

```sh
git clone https://github.com/canyon-velvet/email-agent.git
cd email-agent
uv sync
```

## Run

```sh
uv run email-agent --version
uv run email-agent --help
```

## Develop

```sh
uv run pytest            # tests
uv run ruff check .      # lint
uv run ruff format .     # format
```

CI runs the lint, a format check, and the tests on every pull request and on every push to `main`.
