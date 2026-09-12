# Decompiler Noise Guide

These differences are usually weak evidence.

## Names And Addresses

- `sub_401000` vs `sub_7A10`
- `v1`, `v2`, `a1`, `result`
- stack offsets such as `[sp+20h] [bp-1E0h]`
- register comments such as `// r0`
- IDA labels such as `loc_`, `off_`, `byte_`, `dword_`

## Type Recovery

Decompilers often disagree on:

- signedness
- `int` vs pointer-looking integer
- `char *` vs `const char *`
- integer width
- `float`/`double` coercion helpers
- structure field types

Treat type differences as important only when they change observable behavior.

## Control Flow Shape

Optimizers and decompilers may render equivalent logic differently:

- `if/else` vs early return
- `switch` vs chained `if`
- inverted conditions
- temporary boolean variables
- duplicated cleanup blocks

Look for the same predicates, side effects, and terminal actions rather than
surface syntax.

## Strong Evidence Despite Noise

These are usually stable:

- distinctive strings and format strings
- unusual constants
- ordered library calls
- parse/validate/convert pipelines
- error-reporting and exit behavior
- allocation/free ownership patterns
- file/network/crypto side effects
