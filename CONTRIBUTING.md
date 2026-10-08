# Contributing to homology-operator

[中文](CONTRIBUTING.zh-CN.md) · [Development](docs/en/VALIDATION.md)

Documentation, examples, input validation, correctness, performance and platform
improvements are welcome. Read [project conventions](AGENTS.md) and the relevant
mathematical contract first. Keep changes small and describe the trigger, final
behavior, checks actually run, skipped checks and remaining limitations.

1. Update both language entries, relevant API docs, comments, examples and tests
   for public behavior changes.
2. Validate projection legality independently, including cycle homology preservation.
   Feasibility, current objective and global optimality are separate claims.
3. Keep `selected_mass` distinct from true minimum class mass. Independent PH and
   GUDHI comparisons must not fill production results.
4. For native changes, rebuild the matching extension and require native tests.
5. Bind performance claims to source/build/input, arithmetic, certificate and budget,
   and retain complete costs, failures and regressions.
6. Do not commit environments, build caches, wheels or temporary measurements.
   Keep temporary measurements and research material in ignored directories.

At minimum, run the applicable checks from [development](docs/en/VALIDATION.md).
Documentation edits require source-link checks and both strict site builds;
modified Python snippets must actually run. Mathematical or serialization changes
need independent invariants and rejection/round-trip evidence.

Report problems through [GitHub Issues](https://github.com/proffitteoy/homology-operator/issues).
The project uses MIT; the 0.x compatibility policy and Trusted Publisher procedure
are in [public releases](docs/en/VALIDATION.md#public-releases).
