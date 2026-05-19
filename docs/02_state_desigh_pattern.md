# Pipeline Stage Design Pattern

## Purpose

All pipeline stages should be designed for TDD.

Each stage should separate

1. Pure/focussed logic functions that contain the core transformation.
2. Stage harness
3. Pipeline artifact writing

This makes the unit tests simple.

## Stage Harness

The harness is responsible for
- reading input artifacts
- calling logic functions
- writing output JSONL
- writing summary JSON
- writing errors JSONL
returning StageResult

## Output Artifacts
Each stage writes the following with the path provided by StagePaths

- {stage_number}_{artifact_name}.jsonl
- {stage_number}_{artifact_name}.json
- {stage_number}_{artifact_name}_errors.jsonl

## TDD Acceptance Rule
Each stage should have
- pure logic unit tests
- harness tests
- input artifact contract
- output artifact contract
- summary contract
- error contract
- StageReuslt contract.

