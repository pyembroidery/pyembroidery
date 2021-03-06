from .EmbConstant import *
from .EmbThreadPec import get_thread_set
from .PecGraphics import get_blank, draw_scaled
from .WriteHelper import write_int_8, write_int_16le, write_int_16be, \
    write_int_24le, write_string_utf8

SEQUIN_CONTINGENCY = CONTINGENCY_SEQUIN_JUMP
FULL_JUMP = True
MAX_JUMP_DISTANCE = 2047
MAX_STITCH_DISTANCE = 2047

MASK_07_BIT = 0b01111111
JUMP_CODE = 0b00010000
TRIM_CODE = 0b00100000
FLAG_LONG = 0b10000000
PEC_ICON_WIDTH = 48
PEC_ICON_HEIGHT = 38


def write(pattern, f, settings=None):
    f.write(bytes("#PEC0001".encode('utf8')))
    pattern = pattern.copy()
    pattern.convert_stop_to_color_change()
    write_pec(pattern, f)


def write_pec(pattern, f, threadlist=None):
    if threadlist is None:
        pattern.fix_color_count()
        threadlist = pattern.threadlist
    extents = pattern.extents()

    write_pec_header(pattern, f, threadlist)
    write_pec_block(pattern, f, extents)
    write_pec_graphics(pattern, f, extents)


def write_pec_header(pattern, f, threadlist):
    name = pattern.get_metadata("name", "Untitled")
    write_string_utf8(f, "LA:%-16s\r" % name[:8])
    f.write(b'\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\xFF\x00')
    write_int_8(f, int(PEC_ICON_WIDTH / 8))  # PEC BYTE STRIDE
    write_int_8(f, int(PEC_ICON_HEIGHT))  # PEC ICON HEIGHT

    thread_set = get_thread_set()

    if len(thread_set) <= len(threadlist):
        threadlist = thread_set[:]
        # Data is corrupt. Cheat so it won't crash.

    chart = [None] * len(thread_set)
    for thread in set(threadlist):
        index = thread.find_nearest_color_index(thread_set)
        thread_set[index] = None
        chart[index] = thread

    color_index_list = []
    for thread in threadlist:
        color_index_list.append(thread.find_nearest_color_index(chart))

    current_thread_count = len(color_index_list)
    if current_thread_count is not 0:
        f.write(b'\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20')
        add_value = current_thread_count - 1
        color_index_list.insert(0, add_value)
        f.write(bytes(bytearray(color_index_list)))
    else:
        f.write(b'\x20\x20\x20\x20\x64\x20\x00\x20\x00\x20\x20\x20\xFF')

    for i in range(current_thread_count, 463):
        f.write(b'\x20')  # 520


def write_pec_block(pattern, f, extents):
    width = extents[2] - extents[0]
    height = extents[3] - extents[1]

    stitch_block_start_position = f.tell()
    f.write(b'\x00\x00')
    write_int_24le(f, 0)  # Space holder.
    f.write(b'\x31\xff\xf0')
    write_int_16le(f, int(round(width)))
    write_int_16le(f, int(round(height)))
    write_int_16le(f, 0x1E0)
    write_int_16le(f, 0x1B0)

    write_int_16be(f, 0x9000 | -int(round(extents[0])))
    write_int_16be(f, 0x9000 | -int(round(extents[1])))

    pec_encode(pattern, f)

    stitch_block_length = f.tell() - stitch_block_start_position

    current_position = f.tell()
    f.seek(stitch_block_start_position + 2, 0)
    write_int_24le(f, stitch_block_length)
    f.seek(current_position, 0)


def write_pec_graphics(pattern, f, extents):
    blank = get_blank()
    for block in pattern.get_as_stitchblock():
        stitches = block[0]
        draw_scaled(extents, stitches, blank, 6, 4)
    f.write(bytes(bytearray(blank)))

    for block in pattern.get_as_colorblocks():
        stitches = [s for s in block[0] if s[2] == STITCH]
        blank = get_blank()  # [ 0 ] * 6 * 38
        draw_scaled(extents, stitches, blank, 6)
        f.write(bytes(bytearray(blank)))


def encode_long_form(value):
    value &= 0b0000111111111111
    value |= 0b1000000000000000
    return value


def flag_jump(longForm):
    return longForm | (JUMP_CODE << 8)


def flag_trim(longForm):
    return longForm | (TRIM_CODE << 8)


def pec_encode(pattern, f):
    color_two = True
    xx = 0
    yy = 0
    for stitch in pattern.stitches:
        x = stitch[0]
        y = stitch[1]
        data = stitch[2]
        dx = int(round(x - xx))
        dy = int(round(y - yy))
        xx += dx
        yy += dy
        if data in (STITCH, JUMP, TRIM):
            if data == STITCH and -64 < dx < 63 and -64 < dy < 63:
                f.write(bytes(bytearray([dx & MASK_07_BIT, dy & MASK_07_BIT])))
            else:
                dx = encode_long_form(dx)
                dy = encode_long_form(dy)

                if data == JUMP:
                    dx = flag_jump(dx)
                    dy = flag_jump(dy)
                elif data == TRIM:
                    dx = flag_trim(dx)
                    dy = flag_trim(dy)

                data = [
                    (dx >> 8) & 0xFF,
                    dx & 0xFF,
                    (dy >> 8) & 0xFF,
                    dy & 0xFF]
                f.write(bytes(bytearray(data)))
        elif data == COLOR_CHANGE:
            f.write(b'\xfe\xb0')
            if color_two:
                f.write(b'\x02')
            else:
                f.write(b'\x01')
            color_two = not color_two
        elif data == STOP:
            # This should never happen because we've converted each STOP into a
            # color change to the same color.
            pass
        elif data == END:
            f.write(b'\xff')
