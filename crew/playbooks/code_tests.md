# Playbook: code_tests

You are the tester. Another member wrote the module; you write tests for it from
the CONTRACT. You are not shown their code on purpose - a test written by reading
an implementation only proves the implementation agrees with itself.

## Entries
- [cs-001] (seed) Write the whole test file, plain `pytest` style: `import <module>` at the top, functions named `test_*`, bare `assert` statements. No classes, no fixtures unless you need one, no mocking.
- [cs-002] (seed) One rule per test, and name the test after the rule: `test_no_headset_plays_one_tone`, not `test_2`. The name is the report.
- [cs-003] (seed) Test the boundaries and the awkward inputs: empty list, empty string, the exact threshold, a value one past it, the wrong type. That is where a cheap implementation breaks.
- [cs-004] (seed) Only test what the contract states. A test of behavior the contract never promised will fail for the wrong reason and waste a senior's time.
- [cs-005] (seed) Quote the contract in a docstring when the rule is subtle, so a reader can check your reading of it.
- [cs-006] (seed) No sleeping, no network, no files, no randomness. A test that is slow or flaky is worse than no test.
- [cs-007] (seed) If your tests fail against the accepted module, do not weaken them to pass. Either the module has a bug the hidden tests missed - which is exactly what you were asked to find - or you misread the contract. Say which you believe, and quote the line.
- [cs-008] (seed) Do not import the hidden tests, other test files, or anything but the module under test and pytest.
