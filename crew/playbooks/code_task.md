# Playbook: code_task

You are writing one complete Python module against a contract. The harness runs
tests you never see against it. You cannot argue with them; you can only satisfy
the contract.

## Entries
- [ct-001] (seed) Write the WHOLE file every time, from the first line to the last. Not a diff, not "the rest is unchanged", not a fragment. A partial file is a failed task.
- [ct-002] (seed) The contract's API block is exact. Every name in it must exist at module level, spelled the same way, including constants. Renaming something to what you think is clearer fails the task.
- [ct-003] (seed) Only the imports the contract allows. Anything that touches the filesystem, network, registry, audio device or another process is passed IN to your functions by the caller; if you feel you need `os`, `subprocess`, `socket` or `open()`, you have misread the contract.
- [ct-004] (seed) No stubs. `pass`, `...` and `raise NotImplementedError` in a required function are failures, not progress.
- [ct-005] (seed) Read the worked examples as tests. Every example table in a contract is a case that will be checked; walk through your code with each row before you submit.
- [ct-006] (seed) Rules are ordered for a reason. When a contract numbers its rules, apply them in that order - the first match wins, and a later rule must not override an earlier one.
- [ct-007] (seed) Do not mutate what you are given. Return new values; the tests check that the caller's list or dataclass is unchanged.
- [ct-008] (seed) Exact return shapes. If the contract says a dict with four keys, return those four keys and no others; if it says an int, do not return a float.
- [ct-009] (seed) `True`/`False` means the object `True`/`False`. Tests use `is True`, so return real booleans, not 1, 0, or a truthy string.
- [ct-010] (seed) When the feedback quotes a failing test, fix the cause the test names. Do not rewrite the parts that already pass; a regression loses work you had already banked.
- [ct-011] (seed) If you believe the contract is wrong or contradicts itself, say so in a NOTE line at the end of your answer AND still implement the contract as written. The note reaches a human; guessing does not.
- [ct-012] (seed) An accepted module from another member is a dependency, not a suggestion: import it by name and use it. Re-implementing its logic yourself is a failure even if your version works.
