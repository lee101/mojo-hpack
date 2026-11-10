from std.sys import simd_width_of

comptime P64 = Pointer[UInt64, AnyOrigin[mut=True]]

@export("p3_shift")
def p3_shift(addr: Int, n: Int) abi("C") -> UInt64:
    var p = P64(unsafe_from_address=addr)
    var v = p.unsafe_load[width=4](0)
    var amt = p.unsafe_load[width=4](4)
    var r = (v << amt) | (v >> (UInt64(64) - amt))
    var out = r[3] + r[1]
    # cross-lane: shift the whole vector by one lane
    var lanes = SIMD[DType.uint64, 4](0, 1, 2, 3)
    var rot = lanes.rotate_left[1]()
    return out + rot[0]

def main():
    print(p3_shift(0, 0))
