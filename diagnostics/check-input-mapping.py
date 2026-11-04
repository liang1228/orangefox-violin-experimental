"""Compile the actual events.cpp scaling/transform code and check screen bounds."""
import subprocess
import sys
import tempfile
from pathlib import Path

source = (Path(sys.argv[1]) / "minuitwrp/events.cpp").read_text()
begin = source.index("static int vk_tp_to_screen(")
end = source.index("\n}", begin) + 2
scale = source[begin:end]
begin = source.index("#ifdef RECOVERY_TOUCHSCREEN_SWAP_XY", end)
end = source.index("\n#ifdef _EVENT_LOGGING", begin)
transform = source[begin:end]
prefix = r"""
#include <cassert>
#include <cstdio>
#define RECOVERY_TOUCHSCREEN_SWAP_XY
#define RECOVERY_TOUCHSCREEN_FLIP_Y
struct range { int minimum, maximum; };
struct position { int x, y; range xi, yi; };
int gr_fb_width() { return 3200; }
int gr_fb_height() { return 2136; }
"""
main = r"""
int main() {
    struct Sample { int rx, ry, sx, sy; } cases[] = {
        {0, 0, 0, 2135}, {213599, 0, 0, 0},
        {0, 319999, 3199, 2135}, {213599, 319999, 3199, 0},
        {106799, 159999, 1599, 1068}
    };
    for (auto c : cases) {
        position p{c.rx, c.ry, {0, 213599}, {0, 319999}};
        int x, y;
        assert(vk_tp_to_screen(&p, &x, &y) == 0);
        TRANSFORM
        assert(x == c.sx && y == c.sy);
        assert(x >= 0 && x < gr_fb_width());
        assert(y >= 0 && y < gr_fb_height());
    }
    puts("PASS: actual C++ mapping, four corners and center within 3200x2136");
}
"""
with tempfile.TemporaryDirectory(prefix="violin-input-") as tmp:
    cpp, binary = Path(tmp) / "mapping.cpp", Path(tmp) / "mapping"
    cpp.write_text(prefix + scale + main.replace("TRANSFORM", transform))
    subprocess.run(["c++", "-std=c++11", str(cpp), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
