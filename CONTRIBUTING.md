# Contributing to Moss Samples

We love your input! We want to make contributing to this project as easy and transparent as possible, whether it's:

- Reporting a bug
- Discussing the current state of the code
- Submitting a fix
- Proposing new features

## We Use [GitHub Flow](https://guides.github.com/introduction/flow/), So All Code Changes Happen Through Pull Requests

Pull requests are the best way to propose changes to the codebase. We actively welcome your pull requests:

1. Fork the repo and create your branch from `main`.
2. If you've added code that should be tested, add tests.
3. If you've changed APIs, update the documentation.
4. Ensure the test suite passes.
5. Make sure your code lints.
6. Issue that pull request!

## Any contributions you make will be under the BSD 2-Clause License

In short, when you submit code changes, your submissions are understood to be under the same [BSD 2-Clause License](LICENSE) that covers the project. Feel free to contact the maintainers if that's a concern.

## Report bugs using GitHub's [issues](https://github.com/usemoss/moss/issues)

We use GitHub issues to track public bugs. Report a bug by [opening a new issue](https://github.com/usemoss/moss/issues/new); it's that easy!

## Report security vulnerabilities privately

Do not open public issues for security vulnerabilities.

Follow [SECURITY.md](SECURITY.md) to report them privately. Prefer GitHub's
[private vulnerability reporting form](https://github.com/usemoss/moss/security/advisories/new)
when enabled; otherwise email `contact@moss.dev`. We aim to acknowledge reports
within 3 business days and provide triage updates on the timeline described in
SECURITY.md.

## Python SDK Development

The Python SDK source lives in [`sdks/python/sdk/`](sdks/python/sdk/). Set up a development environment:

```bash
cd sdks/python/sdk
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Run the tests (cloud/E2E tests auto-skip without credentials):

```bash
pytest tests/
```

Code style is enforced via `black`, `isort`, and `mypy` (see `pyproject.toml` for configuration).

## License

By contributing, you agree that your contributions will be licensed under the BSD 2-Clause License.
