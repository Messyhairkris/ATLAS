"""Hidden tests for std140.py - the author never sees these.

Every number here is a std140 rule: if one is wrong, a shader reads garbage and
nothing reports an error, which is why the tests check bytes, not just offsets.
"""

import struct

import pytest
import std140 as s


# -- base --------------------------------------------------------------------------

@pytest.mark.parametrize("type_name, expected", [
    ("float", (4, 4)), ("int", (4, 4)), ("uint", (4, 4)), ("bool", (4, 4)),
    ("vec2", (8, 8)), ("ivec2", (8, 8)), ("bvec2", (8, 8)),
    ("vec3", (16, 12)), ("uvec3", (16, 12)),
    ("vec4", (16, 16)), ("ivec4", (16, 16)),
    ("mat2", (16, 32)), ("mat3", (16, 48)), ("mat4", (16, 64)),
])
def test_base_alignment_and_size(type_name, expected):
    assert s.base(type_name) == expected


def test_unknown_types_are_refused():
    for bad in ("double", "dvec3", "mat3x4", "sampler2D", "", "Vec3"):
        with pytest.raises(ValueError):
            s.base(bad)


def test_the_tables_are_complete():
    assert set(s.SCALARS) == {"float", "int", "uint", "bool"}
    assert s.VECTORS["ivec3"] == ("int", 3)
    assert s.VECTORS["bvec4"] == ("bool", 4)
    assert len(s.VECTORS) == 12
    assert s.MATRICES == {"mat2": 2, "mat3": 3, "mat4": 4}


# -- parse -------------------------------------------------------------------------

def test_parse_reads_plain_and_array_members():
    assert s.parse("vec3 lightDir") == ("vec3", "lightDir", 0)
    assert s.parse("  float weights[4];") == ("float", "weights", 4)
    assert s.parse("mat4 mvp[2]") == ("mat4", "mvp", 2)
    assert s.parse("int _count ;") == ("int", "_count", 0)


def test_parse_refuses_what_glsl_would_refuse():
    for bad in ("double d", "float x[0]", "float 2x", "vec3", "float x[-1]",
                "float x[]", ""):
        with pytest.raises(ValueError):
            s.parse(bad)


# -- layout: the contract table, row by row ----------------------------------------

def offsets(decls):
    return [m["offset"] for m in s.layout(decls)["members"]]


def test_a_float_fits_into_a_vec3s_padding():
    """The famous trap: vec3 is aligned to 16 but only 12 long."""
    info = s.layout(["vec3 lightDir", "float intensity"])
    assert offsets(["vec3 lightDir", "float intensity"]) == [0, 12]
    assert info["size"] == 16


def test_mixed_members_follow_rule_three():
    decls = ["float a", "vec3 b", "float c", "vec2 d"]
    assert offsets(decls) == [0, 16, 28, 32]
    assert s.layout(decls)["size"] == 48


def test_every_array_element_is_padded_to_sixteen_even_a_float():
    info = s.layout(["float weights[4]", "int count"])
    weights = info["members"][0]
    assert (weights["stride"], weights["size"], weights["align"]) == (16, 64, 16)
    assert info["members"][1]["offset"] == 64
    assert info["size"] == 80


def test_a_mat3_is_three_padded_columns():
    info = s.layout(["mat3 normal", "vec4 tint"])
    assert info["members"][0]["size"] == 48
    assert offsets(["mat3 normal", "vec4 tint"]) == [0, 48]
    assert info["size"] == 64


def test_an_array_of_matrices():
    info = s.layout(["mat4 mvp[2]", "bool lit"])
    mvp = info["members"][0]
    assert (mvp["stride"], mvp["size"]) == (64, 128)
    assert info["members"][1]["offset"] == 128
    assert info["size"] == 144


def test_vec2s_pack_tightly():
    assert offsets(["vec2 uv", "vec2 size", "float t"]) == [0, 8, 16]
    assert s.layout(["vec2 uv", "vec2 size", "float t"])["size"] == 32


def test_a_vec2_after_a_float_is_aligned_to_eight():
    assert offsets(["float a", "vec2 b"]) == [0, 8]


def test_a_vec3_array_has_a_stride_of_sixteen():
    member = s.layout(["vec3 points[3]"])["members"][0]
    assert (member["stride"], member["size"]) == (16, 48)


def test_member_records_have_every_field():
    member = s.layout(["vec3 v"])["members"][0]
    assert member == {"name": "v", "type": "vec3", "count": 0, "offset": 0,
                      "align": 16, "size": 12, "stride": 0}


def test_the_block_size_is_a_multiple_of_sixteen():
    assert s.layout(["float a"])["size"] == 16
    assert s.layout([])["size"] == 0


def test_duplicate_names_are_refused():
    with pytest.raises(ValueError):
        s.layout(["float a", "vec2 a"])


# -- pack ----------------------------------------------------------------------------

def test_pack_matches_the_contract_example_byte_for_byte():
    data = s.pack(["vec3 lightDir", "float intensity"],
                  {"lightDir": [1, 2, 3], "intensity": 0.5})
    assert data.hex() == "0000803f00000040000040400000003f"


def test_pack_is_exactly_the_layout_size():
    decls = ["float a", "vec3 b", "float c", "vec2 d"]
    data = s.pack(decls, {"a": 1, "b": [1, 2, 3], "c": 4, "d": [5, 6]})
    assert len(data) == 48


def test_padding_is_zero():
    data = s.pack(["float a", "vec3 b"], {"a": 1.0, "b": [2, 3, 4]})
    assert data[4:16] == bytes(12)          # between a and b
    assert data[28:32] == bytes(4)          # after b, to the block size


def test_ints_uints_and_bools_are_stored_as_integers():
    data = s.pack(["int i", "uint u", "bool yes", "bool no"],
                  {"i": -2, "u": 7, "yes": "anything truthy", "no": 0})
    assert struct.unpack_from("<i", data, 0)[0] == -2
    assert struct.unpack_from("<I", data, 4)[0] == 7
    assert struct.unpack_from("<I", data, 8)[0] == 1
    assert struct.unpack_from("<I", data, 12)[0] == 0


def test_array_elements_land_on_their_stride():
    data = s.pack(["float w[3]"], {"w": [1.0, 2.0, 3.0]})
    assert [struct.unpack_from("<f", data, 16 * i)[0] for i in range(3)] == [1, 2, 3]
    assert data[4:16] == bytes(12)


def test_matrices_are_column_major():
    columns = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
    data = s.pack(["mat3 m"], {"m": columns})
    for c in range(3):
        for r in range(3):
            assert struct.unpack_from("<f", data, 16 * c + 4 * r)[0] == columns[c][r]
        assert data[16 * c + 12:16 * c + 16] == bytes(4)   # each column's padding


def test_an_array_of_mat4():
    identity = [[1 if r == c else 0 for r in range(4)] for c in range(4)]
    twice = [[2 if r == c else 0 for r in range(4)] for c in range(4)]
    data = s.pack(["mat4 mvp[2]", "bool lit"],
                  {"mvp": [identity, twice], "lit": True})
    assert struct.unpack_from("<f", data, 0)[0] == 1
    assert struct.unpack_from("<f", data, 64)[0] == 2
    assert struct.unpack_from("<f", data, 64 + 16 + 4)[0] == 2
    assert struct.unpack_from("<I", data, 128)[0] == 1


def test_ivec_components_are_signed():
    data = s.pack(["ivec2 v"], {"v": [-1, 3]})
    assert struct.unpack_from("<ii", data, 0) == (-1, 3)


def test_extra_values_are_ignored():
    assert len(s.pack(["float a"], {"a": 1, "unused": 99})) == 16


@pytest.mark.parametrize("decls, values", [
    (["float a"], {}),                                   # missing
    (["vec3 v"], {"v": [1, 2]}),                         # short vector
    (["vec2 v"], {"v": [1, 2, 3]}),                      # long vector
    (["float w[3]"], {"w": [1, 2]}),                     # short array
    (["mat2 m"], {"m": [[1, 2, 3], [4, 5, 6]]}),         # wrong column length
    (["mat2 m"], {"m": [[1, 2]]}),                       # too few columns
])
def test_wrong_values_are_refused(decls, values):
    with pytest.raises(ValueError):
        s.pack(decls, values)


# -- glsl_block ----------------------------------------------------------------------

def test_the_glsl_matches_the_contract_exactly():
    assert s.glsl_block("Light", ["vec3 lightDir", "float weights[4]"], 2) == (
        "layout(std140, binding = 2) uniform Light {\n"
        "    vec3 lightDir;\n"
        "    float weights[4];\n"
        "};\n")


def test_the_glsl_is_normalised_through_parse():
    assert s.glsl_block("B", ["  float weights[4];"]) == s.glsl_block(
        "B", ["float weights[4]"])
    assert s.glsl_block("B", ["mat4 m"]).startswith(
        "layout(std140, binding = 0) uniform B {")


def test_the_glsl_refuses_a_bad_declaration():
    with pytest.raises(ValueError):
        s.glsl_block("B", ["double d"])
