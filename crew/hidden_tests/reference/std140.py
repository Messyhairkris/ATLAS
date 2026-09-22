"""Reference implementation of contracts/gl_std140.md (never given to the crew)."""

import re
import struct

SCALARS = ("float", "int", "uint", "bool")
VECTORS = {f"{p}vec{n}": (s, n) for p, s in (("", "float"), ("i", "int"),
                                             ("u", "uint"), ("b", "bool"))
           for n in (2, 3, 4)}
MATRICES = {"mat2": 2, "mat3": 3, "mat4": 4}
FORMATS = {"float": "<f", "int": "<i", "uint": "<I", "bool": "<I"}
_DECL = re.compile(r"^\s*([A-Za-z0-9_]+)\s+([A-Za-z_][A-Za-z0-9_]*)"
                   r"\s*(?:\[\s*(\d+)\s*\])?\s*;?\s*$")


def _round_up(value: int, multiple: int) -> int:
    return -(-value // multiple) * multiple


def base(type_name: str) -> tuple:
    """(alignment, size) of one non-array value of this type."""
    if type_name in SCALARS:
        return 4, 4
    if type_name in VECTORS:
        n = VECTORS[type_name][1]
        return (8, 8) if n == 2 else (16, 4 * n)
    if type_name in MATRICES:
        return 16, 16 * MATRICES[type_name]
    raise ValueError(f"unknown GLSL type {type_name!r}")


def parse(decl: str) -> tuple:
    """'float weights[4]' -> ('float', 'weights', 4); no array -> count 0."""
    match = _DECL.match(decl or "")
    if not match:
        raise ValueError(f"not a declaration: {decl!r}")
    type_name, name, count = match.group(1), match.group(2), match.group(3)
    base(type_name)
    count = int(count) if count else 0
    if count == 0 and match.group(3) is not None:
        raise ValueError("an array needs at least one element")
    return type_name, name, count


def layout(decls: list) -> dict:
    """Offsets, sizes and strides of every member, and the block's total size."""
    members, offset, seen = [], 0, set()
    for decl in decls:
        type_name, name, count = parse(decl)
        if name in seen:
            raise ValueError(f"duplicate member {name!r}")
        seen.add(name)
        align, size = base(type_name)
        if count:
            stride = _round_up(size, 16)
            align = 16
            size = stride * count
        else:
            stride = 0
        offset = _round_up(offset, align)
        members.append({"name": name, "type": type_name, "count": count,
                        "offset": offset, "align": align, "size": size,
                        "stride": stride})
        offset += size
    return {"members": members, "size": _round_up(offset, 16)}


def _components(type_name: str, value) -> list:
    if type_name in SCALARS:
        return [(type_name, value, 0)]
    if type_name in VECTORS:
        scalar, n = VECTORS[type_name]
        if not isinstance(value, (list, tuple)) or len(value) != n:
            raise ValueError(f"{type_name} needs {n} components")
        return [(scalar, v, 4 * i) for i, v in enumerate(value)]
    n = MATRICES[type_name]
    if (not isinstance(value, (list, tuple)) or len(value) != n
            or any(not isinstance(c, (list, tuple)) or len(c) != n for c in value)):
        raise ValueError(f"{type_name} needs {n} columns of {n}")
    return [("float", v, 16 * c + 4 * r)
            for c, column in enumerate(value) for r, v in enumerate(column)]


def pack(decls: list, values: dict) -> bytes:
    """The block's bytes: little-endian, column-major, padding zero."""
    info = layout(decls)
    out = bytearray(info["size"])
    for member in info["members"]:
        if member["name"] not in values:
            raise ValueError(f"no value for {member['name']!r}")
        value = values[member["name"]]
        if member["count"]:
            if not isinstance(value, (list, tuple)) or len(value) != member["count"]:
                raise ValueError(f"{member['name']} needs {member['count']} elements")
            items = [(member["offset"] + i * member["stride"], v)
                     for i, v in enumerate(value)]
        else:
            items = [(member["offset"], value)]
        for start, item in items:
            for scalar, v, at in _components(member["type"], item):
                if scalar == "bool":
                    v = 1 if v else 0
                struct.pack_into(FORMATS[scalar], out, start + at, v)
    return bytes(out)


def glsl_block(name: str, decls: list, binding: int = 0) -> str:
    """The matching GLSL declaration, so the shader and the bytes cannot drift."""
    lines = [f"layout(std140, binding = {binding}) uniform {name} {{"]
    for decl in decls:
        type_name, member, count = parse(decl)
        lines.append(f"    {type_name} {member}{f'[{count}]' if count else ''};")
    lines.append("};")
    return "\n".join(lines) + "\n"
