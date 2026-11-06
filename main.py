import math
import os
import random
import shutil
import sys
import time


T_SIT = 50       # sitting calmly
T_OPEN = 30      # unfolding wings + crouching
PAUSE = 25       # empty ledge before the next pigeon appears
REVEAL = 18      # frames the new pigeon takes to materialise

PERCH_V = 9.6    # height of the ledge surface in model units (v points down)
BIRD_SCALE = 0.50  # how big the pigeon is on screen (smaller = smaller pigeon)

# Flight plan (frames are ~20 per second)
T_CLIMB = 40         # take off and climb up to cruising height
T_CRUISE = 100       # straight, level flight (~5 seconds) while the city scrolls
CRUISE_OX = 14.0     # where the pigeon hangs in the frame while cruising
CRUISE_LIFT = -10.0  # cruising height (negative = up); low enough that raised wings fit on screen
SCROLL_V = 1.4       # city scroll speed in terminal columns per frame
STRIP_EXTRA = 420    # extra skyline width (columns) that scrolls into view


WHITE, SOFT, GREY, SHADE = 231, 255, 254, 253   # the pigeon uses only whites
PINK, BEAK, EYE = 231, 231, 231      # feet, beak, eye ring: white too
HOLE = -1


def capsule(a, b, r0, r1, col):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy or 1e-9
    rm = max(r0, r1)
    bbox = (min(ax, bx) - rm, max(ax, bx) + rm, min(ay, by) - rm, max(ay, by) + rm)

    def test(u, v):
        t = ((u - ax) * dx + (v - ay) * dy) / l2
        t = 0.0 if t < 0 else 1.0 if t > 1 else t
        ex = u - (ax + t * dx)
        ey = v - (ay + t * dy)
        r = r0 + (r1 - r0) * t
        return ex * ex + ey * ey <= r * r

    return bbox, test, col


def ellipse(cu, cv, a, b, rot, col):
    c, s = math.cos(rot), math.sin(rot)
    eu = math.hypot(a * c, b * s)
    ev = math.hypot(a * s, b * c)
    bbox = (cu - eu, cu + eu, cv - ev, cv + ev)
    a2, b2 = a * a, b * b

    def test(u, v):
        du, dv = u - cu, v - cv
        x = du * c + dv * s
        y = -du * s + dv * c
        return x * x / a2 + y * y / b2 <= 1.0

    return bbox, test, col


def polygon(pts, col):
    """Convex polygon (beak)."""
    us = [q[0] for q in pts]
    vs = [q[1] for q in pts]
    bbox = (min(us), max(us), min(vs), max(vs))
    n = len(pts)

    def test(u, v):
        sign = 0
        for i in range(n):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % n]
            cr = (x2 - x1) * (v - y1) - (y2 - y1) * (u - x1)
            if cr != 0:
                sg = 1 if cr > 0 else -1
                if sign == 0:
                    sign = sg
                elif sg != sign:
                    return False
        return True

    return bbox, test, col



def clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else hi if x > hi else x


def smooth(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def lerp(a, b, t):
    return a + (b - a) * t



def stroke_angle(ph):
    return -0.4 + 1.35 * math.sin(ph)


def wing(p, shoulder, n, tones, scale, lag, fold):
    su, sv = shoulder
    shapes = []
    mid = (1.0, 0.0)
    for i in range(n):                           # 0 = leading edge ... n-1 = trailing
        t = i / (n - 1)
        ang = stroke_angle(p - lag * (1 - t))    # outer feathers lag in time
        back = 1.8 * t                           # trailing feathers sweep backwards
        du = math.cos(ang) - back
        dv = math.sin(ang)
        d = math.hypot(du, dv)
        du, dv = du / d, dv / d
        if fold > 0:                             # blend toward "folded along the back"
            fu, fv = -1.0, 0.04 + 0.10 * t
            fd = math.hypot(fu, fv)
            du = du * (1 - fold) + (fu / fd) * fold
            dv = dv * (1 - fold) + (fv / fd) * fold
            d = math.hypot(du, dv)
            du, dv = du / d, dv / d
        if i == n // 2:
            mid = (du, dv)
        ru = su - 3.2 * t                        # roots spread along a short arm
        rv = sv + 0.9 * t
        length = (17.0 - 8.5 * t) * scale * (1 - 0.4 * fold)
        tip = (ru + du * length, rv + dv * length)
        shapes.append(capsule((ru, rv), tip, 1.7 - 0.4 * t, 0.9 - 0.2 * t, tones[i % 2]))
    L = 17.0 * scale * (1 - 0.4 * fold)
    blade = ellipse(su - 1.6 + mid[0] * 0.42 * L, sv + 0.4 + mid[1] * 0.42 * L,
                    0.40 * L, lerp(3.6, 1.9, fold) * scale,
                    math.atan2(mid[1], mid[0]), tones[0])
    shapes.insert(0, blade)
    shapes.append(ellipse(su - 1.4, sv + 0.5, 4.4, 2.4, -0.25, tones[2]))
    return shapes


def pigeon(P):
    th, ox, oy = P["pitch"], P["ox"], P["oy"]
    c, s = math.cos(th), math.sin(th)

    def to_model(wu, wv):                        # world point -> bird-local point
        pu, pv = wu - ox, wv - oy
        return pu * c + pv * s, -pu * s + pv * c

    fold, p, legs, hb = P["fold"], P["p"], P["legs"], P["hb"]
    sh = []

    sh += wing(p - 0.45, (1.6, -3.6), 10, (GREY, SHADE, GREY), 0.9, 0.3, fold)

    spread = 0.12 + (0.03 * math.sin(p) if not fold else 0.0)
    for i in range(7):
        ang = math.pi - 0.14 + (i - 3) * spread
        root = (-7.2, 1.0)
        tip = (root[0] + 10.5 * math.cos(ang), root[1] + 10.5 * math.sin(ang))
        tone = SHADE if i in (0, 6) else (SOFT if i % 2 else WHITE)
        sh.append(capsule(root, tip, 0.9, 0.7, tone))
    sh.append(ellipse(-6.4, 1.0, 3.0, 2.1, 0.0, SOFT))

    foot_v = PERCH_V - 0.25
    hips = [(-1.2, 4.3), (0.8, 4.6)]
    stand = [(-1.8, foot_v), (0.9, foot_v)]
    tuck = [(-4.4, 7.3), (-2.3, 7.7)]
    for hip, sw, tk in zip(hips, stand, tuck):
        fm = to_model(*sw)
        foot = (lerp(fm[0], tk[0], legs), lerp(fm[1], tk[1], legs))
        tm = to_model(sw[0] + 1.9, sw[1])
        toe = (lerp(tm[0], tk[0] - 1.7, legs), lerp(tm[1], tk[1] - 0.2, legs))
        sh.append(capsule(hip, foot, 0.6, 0.4, PINK))
        sh.append(capsule(foot, toe, 0.4, 0.3, PINK))

    sh.append(ellipse(0.0, 0.5, 9.0, 4.9, -0.15, WHITE))
    sh.append(ellipse(-0.3, 2.9, 7.8, 2.3, -0.12, SOFT))
    sh.append(ellipse(5.6, 0.3, 4.4, 4.4, 0.0, WHITE))


    nu, nv = -0.9 * fold, 0.9 * fold                 # neck sinks while sitting
    hu, hv = -2.3 * fold, hb + 1.9 * fold            # head tucks in, hunched
    sh.append(ellipse(8.0 + nu, -2.6 + nv, 3.6, 3.6, 0.5, WHITE))
    sh.append(ellipse(8.4 + nu, -1.9 + nv, 2.6, 2.8, 0.5, SOFT))
    sh.append(ellipse(10.4 + hu, -4.8 + hv, 3.0, 2.8, 0.0, WHITE))
    sh.append(polygon([(12.6 + hu, -6.2 + hv), (16.0 + hu, -4.8 + hv),
                       (12.6 + hu, -3.4 + hv)], BEAK))
    sh.append(ellipse(13.1 + hu, -5.6 + hv, 0.9, 0.7, 0.0, WHITE))      # cere
    if P["blink"]:                                   # eye CLOSED: a thin dark line
        sh.append(ellipse(11.6 + hu, -5.5 + hv, 1.5, 0.6, 0.0, HOLE))
    else:                                            # eye open: ring + empty pupil
        sh.append(ellipse(11.6 + hu, -5.5 + hv, 1.3, 1.3, 0.0, EYE))
        sh.append(ellipse(11.6 + hu, -5.5 + hv, 0.95, 0.95, 0.0, HOLE))

    # near wing on top
    near = (GREY, SHADE, SOFT) if fold > 0.5 else (WHITE, SOFT, WHITE)
    sh += wing(p, (3.4, -3.0), 11, near, 1.0, 0.3, fold)
    return sh


def pose(f):
    P = dict(ox=0.0, oy=0.0, pitch=-0.12, fold=1.0, p=-math.pi / 2,
             legs=0.0, blink=False, hb=0.0, wind=0.0, flying=False, scroll=0.0)
    if f < T_SIT:                                  # 1. sitting
        P["hb"] = 0.45 * math.sin(f * 0.28)
        P["oy"] = 0.12 * math.sin(f * 0.18)        # breathing
        P["blink"] = True                          # sleeping: eyes closed
    elif f < T_SIT + T_OPEN:                       # 2. unfold wings + crouch
        k = (f - T_SIT) / T_OPEN
        crouch = smooth((k - 0.4) / 0.6)
        P["fold"] = 1 - smooth(k / 0.6)
        P["oy"] = 1.3 * crouch
        P["pitch"] = lerp(-0.12, -0.10, crouch)
        P["blink"] = k < 0.35                      # eyes open as it wakes up
    else:                                          # 3. take off, cruise, leave
        t = f - T_SIT - T_OPEN
        x = clamp(t / T_CLIMB)
        P["fold"] = 0.0
        P["flying"] = True
        P["p"] = -math.pi / 2 + 0.40 * t           # flap phase keeps running
        P["legs"] = smooth(t / 14)                 # feet leave the ledge, tuck up
        P["wind"] = smooth((t - 10) / 30)

        lift = lerp(1.3, CRUISE_LIFT, smooth(x))
        P["oy"] = lift - 0.8 * math.cos(P["p"]) * smooth(t / 20)
        P["pitch"] = lerp(-0.10, -0.04, smooth(x)) - 0.22 * math.sin(math.pi * x)

    
        if t <= T_CLIMB + T_CRUISE:
            P["ox"] = CRUISE_OX * smooth(x)
        else:
            t2 = t - T_CLIMB - T_CRUISE
            P["ox"] = CRUISE_OX + 0.3 * t2 + 0.045 * t2 * t2

        if t <= T_CLIMB:
            P["scroll"] = SCROLL_V * T_CLIMB * (x ** 3 - x ** 4 / 2)
        else:
            P["scroll"] = SCROLL_V * T_CLIMB * 0.5 + SCROLL_V * (t - T_CLIMB)
    return P



BIT_ROWS, BIT_LEN = 200, 512
BITS = [[random.choice("01") for _ in range(BIT_LEN)] for _ in range(BIT_ROWS)]


def layout(cols, rows):
    base = min(3.0, (rows - 1) / 31.0, cols / 100.0)
    sy = base * BIRD_SCALE
    sx = sy * 2.0                                  # terminal cells are ~2x taller than wide
    cx0 = cols * 0.30                              # where the pigeon sits
    cy0 = rows * 0.66 - PERCH_V * sy               # rooftop ledge at 66% of the height
    return sx, sy, cx0, cy0



BODY, WIN_LIT, LEDGE = 236, 222, 252               # building, lit window, roof edge


def make_scene(cols, rows, seed=5):
    sx, sy, cx0, cy0 = layout(cols, rows)
    perch_y = int(cy0 + PERCH_V * sy)
    rnd = random.Random(seed)
    width = cols + STRIP_EXTRA
    layer = [[None] * width for _ in range(rows)]
    windows = []                                  

    def put(x, y, col):
        if 0 <= x < width and 0 <= y < rows:
            layer[y][x] = col

    def paint(win):
        x, y, lit = win
        put(x, y, WIN_LIT if lit else None)     
        put(x + 1, y, WIN_LIT if lit else None)

    clear_lo, clear_hi = cx0 - 24 * sx, cx0 + 22 * sx
    x = 0
    while x < width:
        w = rnd.choice((10, 12, 14, 16))
        behind_pigeon = x + w > clear_lo and x < clear_hi
        frac = rnd.uniform(0.08, 0.14) if behind_pigeon else rnd.uniform(0.22, 0.50)
        top = perch_y - max(2, int(perch_y * frac))
        for yy in range(top, perch_y):
            for xx in range(x, x + w - 1):         
                put(xx, yy, BODY)
        for wy in range(top + 1, perch_y - 1, 2):
            for wx in range(x + 1, x + w - 3, 4):
                win = [wx, wy, rnd.random() < 0.35]
                windows.append(win)
                paint(win)
        x += w

    for y in range(max(0, perch_y), rows):
        for xx in range(width):
            put(xx, y, LEDGE if y == perch_y else 244 if y == perch_y + 1 else 235)

    return dict(layer=layer, windows=windows, perch_y=perch_y, paint=paint, width=width)


def flicker(scene):
    if scene["windows"]:
        win = random.choice(scene["windows"])
        win[2] = not win[2]
        scene["paint"](win)


def raster(grid, shapes, cx0, cy0, sx, sy, ox, oy, th, cols, rows):
    c, s = math.cos(th), math.sin(th)
    for (u0, u1, v0, v1), test, col in shapes:
        wus, wvs = [], []
        for u, v in ((u0, v0), (u1, v0), (u0, v1), (u1, v1)):
            wus.append(ox + u * c - v * s)
            wvs.append(oy + u * s + v * c)
        x_lo = max(0, int(math.floor(cx0 + min(wus) * sx)))
        x_hi = min(cols - 1, int(math.ceil(cx0 + max(wus) * sx)))
        y_lo = max(0, int(math.floor(cy0 + min(wvs) * sy)))
        y_hi = min(rows - 1, int(math.ceil(cy0 + max(wvs) * sy)))
        for y in range(y_lo, y_hi + 1):
            wv = (y + 0.5 - cy0) / sy - oy
            row = grid[y]
            for x in range(x_lo, x_hi + 1):
                wu = (x + 0.5 - cx0) / sx - ox
                if test(wu * c + wv * s, -wu * s + wv * c):
                    row[x] = col


def render(cols, rows, P, scene, reveal=1.0):
    sx, sy, cx0, cy0 = layout(cols, rows)
    perch_y = scene["perch_y"]

    # --- the pigeon
    grid = [[None] * cols for _ in range(rows)]
    ox_cells, flow, off = 0, 0, 0
    if P:
        raster(grid, pigeon(P), cx0, cy0, sx, sy, P["ox"], P["oy"], P["pitch"], cols, rows)
        ox_cells = int(P["ox"] * sx)
        off = int(P["scroll"])                     
        flow = int(P["ox"] * 3) + off     

    halo = [[False] * cols for _ in range(rows)]
    for y in range(rows):
        row = grid[y]
        for x in range(cols):
            if row[x] is not None and row[x] != HOLE:
                for yy in (y - 1, y, y + 1):
                    if 0 <= yy < perch_y:
                        hr = halo[yy]
                        for xx in range(max(0, x - 2), min(cols, x + 3)):
                            hr[xx] = True

    out = []
    for y in range(rows):
        line, last = [], None
        bits = BITS[y % BIT_ROWS]
        lay, width = scene["layer"][y], scene["width"]
        for x in range(cols):
            col = grid[y][x]
            ch = " "
            if col is not None and col != HOLE and reveal < 1.0:
                if ((x * 73856093) ^ (y * 19349663)) % 100 >= reveal * 100:
                    col = None                     # not materialised yet
            if col == HOLE:
                col = None                         # the eye: an empty gap
            elif col is not None:
                ch = bits[(x - ox_cells + flow) % BIT_LEN]
            elif not halo[y][x]:
                col = lay[(x + off) % width]
                if col is not None:
                    ch = "1" if col in (WIN_LIT, LEDGE) else "0"
            if col is None:
                ch = " "
            if col != last:
                line.append("\033[0m" if col is None else f"\033[38;5;{col}m")
                last = col
            line.append(ch)
        out.append("".join(line) + "\033[0m")
    return "\n".join(out)


def tail_is_offscreen(cols, rows, P):
    sx, sy, cx0, cy0 = layout(cols, rows)
    return cx0 + (P["ox"] - 20) * sx > cols


def main():
    os.system("")  
    cols, rows = shutil.get_terminal_size((100, 34))
    rows -= 1
    city = 0                                       
    scene = make_scene(cols, rows, 5 + city)
    sys.stdout.write("\033[2J\033[?25l")
    f = 0
    try:
        while True:
            t0 = time.time()
            c, r = shutil.get_terminal_size((100, 34))
            r -= 1
            if (c, r) != (cols, rows):
                cols, rows = c, r
                scene = make_scene(cols, rows, 5 + city)
                sys.stdout.write("\033[2J")

            P = pose(f) if f >= 0 else None
            reveal = clamp(f / REVEAL) if f >= 0 else 1.0
            sys.stdout.write("\033[H" + render(cols, rows, P, scene, reveal))
            sys.stdout.flush()

            if f % 12 == 0:
                flicker(scene)                     # a window switches on/off now and then
            f += 1
            if P and P["flying"] and tail_is_offscreen(cols, rows, P):
                f = -PAUSE                         # gone! empty ledge, then start over
                city += 1                          # ...in front of a brand-new city
                scene = make_scene(cols, rows, 5 + city)
            time.sleep(max(0.0, 0.05 - (time.time() - t0)))
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\033[?25h\033[0m\n")


if __name__ == "__main__":
    main()
