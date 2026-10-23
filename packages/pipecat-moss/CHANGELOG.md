# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `MossRetrievalService(cache_path=...)` keeps downloaded indexes on disk, so a load in a new process reads an unchanged index from disk instead of downloading it.
- `load_index(index_name, auto_refresh=...)`.

### Changed
- Requires `moss` 1.14.0 or later.

### Fixed
- `MossIndexProcessor` forwards the frame it received instead of building a new one, so `LLMContextFrame.speculation` and `LLMMessagesUpdateFrame.run_llm` reach the LLM.
- `project_id` and `project_key` fall back to `MOSS_PROJECT_ID` and `MOSS_PROJECT_KEY` as documented. Missing credentials raise `ValueError`.

## [0.0.5] - 2026-07-14

### Changed
- Bumped `pipecat-ai` minimum from `>=1.1.0` to `>=1.5.0`.

## [0.0.4] - 2026-05-01

### Changed
- Updated `requires-python` from `>=3.10` to `>=3.11` to match `pipecat-ai 1.1.0` requirements.

## [0.0.3] - 2026-03-24

### Added
- Supports latest version of moss

## [0.0.2] - 2026-01-18

### Added

- Support for Pipecat v0.0.99.
- Support for LLMContext and LLMContextAggregatorPair
- removed deprecated OpenAILLMContext and OpenAILLMContextAggregatorPair

## [0.0.1] - 2025-12-29

### Added

- Initial release of `pipecat-moss` integration.
- `MossRetrievalService` for augmenting Pipecat LLM contexts with retrieved documents
- Example `moss-retrieval-demo.py` demonstrating a full voice pipeline with retrieval.
- `moss-create-index-demo.py` for creating and populating a Moss index.