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

In short, when you submit code changes, your submissions are understood to be under the same [BSD 2-Clause License](LICENSE) that covers the project. The SDKs in `sdks/` are the exception: they are under the PolyForm Shield License, as their `LICENSE.txt` states. Feel free to contact the maintainers if that's a concern.

## Report bugs using GitHub's [issues](https://github.com/usemoss/moss/issues)

We use GitHub issues to track public bugs. Report a bug by [opening a new issue](https://github.com/usemoss/moss/issues/new); it's that easy!

## SDKs

`sdks/javascript/sdk`, `sdks/python/sdk` and `sdks/elixir/sdk` hold the source and samples of the latest release of each SDK, for reading. Each release replaces them, so they carry no build or test setup, and each iOS release replaces `sdks/swift/Sources` the same way. Install the SDKs from npm (`@moss-js/moss`), PyPI (`moss`), Hex (`moss`) or Swift Package Manager.

Pull requests against these folders are welcome. Maintainers bring an accepted change into the SDK's next release, thank its author in that release's CHANGELOG, and close the pull request with a link to the release. Pull requests against `sdks/go` merge here as usual.

## License

By contributing, you agree that your contributions will be licensed under the BSD 2-Clause License, or under the PolyForm Shield License for the SDKs in `sdks/`.
