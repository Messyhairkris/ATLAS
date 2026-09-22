# Contract: std140.py — OpenGL uniform blocks, byte for byte

One self-contained Python module, `std140.py`, that lays out and packs an OpenGL
uniform block under GLSL's **std140** rules, so Python code (PyOpenGL, moderngl) can
fill a uniform buffer the shader will read correctly — and can print the matching
GLSL declaration so the two never drift apart.

std140 is where OpenGL programs go quietly wrong: a `vec3` takes 16 bytes of
alignment but only 12 of space, and every array element is padded to 16 bytes, even a
`float`. Get one offset wrong and the shader reads garbage with no error anywhere.

## Public API (all of these names must exist)

```python
SCALARS = ("float", "int", "uint", "bool")
VECTORS = {...}      # "vec2".."vec4", "ivec2".."ivec4", "uvec2".."uvec4", "bvec2".."bvec4"
                     # -> (scalar type, component count), e.g. "ivec3": ("int", 3)
MATRICES = {"mat2": 2, "mat3": 3, "mat4": 4}

def base(type_name: str) -> tuple: ...           # (alignment, size) of ONE value
def parse(decl: str) -> tuple: ...               # (type, name, count)
def layout(decls: list) -> dict: ...
def pack(decls: list, values: dict) -> bytes: ...
def glsl_block(name: str, decls: list, binding: int = 0) -> str: ...
```

Allowed imports: `struct`, `re`, `math`. Nothing else.

## base(type_name) — one value, not an array

Rules, in this order; anything else is a `ValueError`:

1. a scalar (`float`, `int`, `uint`, `bool`) → `(4, 4)`
2. a 2-component vector (`vec2`, `ivec2`, `uvec2`, `bvec2`) → `(8, 8)`
3. a 3-component vector → `(16, 12)` — aligned like a vec4, but only 12 bytes long
4. a 4-component vector → `(16, 16)`
5. a matrix `matN` is stored as N column vectors, each padded to 16 bytes →
   `(16, 16 * N)`: `mat2` → `(16, 32)`, `mat3` → `(16, 48)`, `mat4` → `(16, 64)`

A `bool` is stored as a 4-byte unsigned integer, 1 or 0.

## parse(decl)

Reads one member declaration: `"<type> <name>"` or `"<type> <name>[<count>]"`, with
optional surrounding whitespace and an optional trailing `;`.

- returns `(type, name, count)`, where `count` is `0` for a non-array member;
- the name follows the GLSL identifier rule: a letter or `_`, then letters, digits, `_`;
- an unknown type, an unreadable declaration, or `[0]` is a `ValueError`.

| decl | result |
|---|---|
| `"vec3 lightDir"` | `("vec3", "lightDir", 0)` |
| `"  float weights[4];"` | `("float", "weights", 4)` |
| `"mat4 mvp[2]"` | `("mat4", "mvp", 2)` |
| `"double d"` | `ValueError` |
| `"float x[0]"` | `ValueError` |

## layout(decls)

Members are placed in order. Returns:

```python
{"members": [{"name": str, "type": str, "count": int,
              "offset": int, "align": int, "size": int, "stride": int}, ...],
 "size": int}
```

Rules:

1. **A non-array member** uses `base(type)`: `align` and `size` as given, `stride` 0.
2. **An array member** (`count > 0`): the element stride is `size` rounded **up** to a
   multiple of 16; `align` is 16; `size` is `stride * count`.
3. Each member's `offset` is the running offset rounded **up** to that member's
   `align`. The running offset then advances by the member's `size`.
4. The block `size` is the final running offset rounded **up** to a multiple of 16.
5. A duplicate member name is a `ValueError`.

Rule 3 is where the famous trap lives: after a `vec3` the running offset is only 12
past it, so a following `float` **fits into the vec3's padding**.

| decls | offsets | block size |
|---|---|---|
| `vec3 lightDir`, `float intensity` | 0, 12 | 16 |
| `float a`, `vec3 b`, `float c`, `vec2 d` | 0, 16, 28, 32 | 48 |
| `float weights[4]`, `int count` | 0 (stride 16, size 64), 64 | 80 |
| `mat3 normal`, `vec4 tint` | 0 (size 48), 48 | 64 |
| `mat4 mvp[2]`, `bool lit` | 0 (stride 64, size 128), 128 | 144 |
| `vec2 uv`, `vec2 size`, `float t` | 0, 8, 16 | 32 |

## pack(decls, values)

Returns exactly `layout(decls)["size"]` bytes.

- `values` maps each member name to its value; a missing name is a `ValueError`.
  Extra names are ignored.
- everything is **little-endian**: `float` as a 32-bit float, `int` as a signed 32-bit
  integer, `uint` and `bool` as unsigned 32-bit integers (`bool`: 1 for truthy, 0 for
  falsy);
- a vector is a list or tuple of exactly its component count, component `i` at
  `offset + 4*i`; the wrong length is a `ValueError`;
- a matrix is a list of N **columns**, each a list of N numbers — column-major, as
  OpenGL expects. Column `c`, row `r` goes at `offset + 16*c + 4*r`. The wrong shape is
  a `ValueError`;
- an array is a list of exactly `count` elements, element `i` at
  `offset + i * stride`; the wrong length is a `ValueError`;
- **every byte not written by a value is zero** — padding included.

Example: `pack(["vec3 lightDir", "float intensity"], {"lightDir": [1, 2, 3],
"intensity": 0.5})` is 16 bytes, hex `0000803f00000040000040400000003f`.

## glsl_block(name, decls, binding=0)

The matching GLSL, so the shader is generated from the same list as the bytes:

```
layout(std140, binding = 2) uniform Light {
    vec3 lightDir;
    float weights[4];
};
```

That is `glsl_block("Light", ["vec3 lightDir", "float weights[4]"], 2)`: one line per
member, four-space indent, arrays written `name[count]`, and a final newline after
`};`. Declarations are normalised through `parse`, so `"  float weights[4];"` prints
the same as `"float weights[4]"`.

## Style

See `HOUSE_STYLE.md`, which is part of this contract.
