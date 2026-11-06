# Terminal Pigeon

An animated ASCII/ANSI pigeon that lives in your terminal. It sleeps on a rooftop ledge in front of a city skyline made of `0`s and `1`s, wakes up, unfolds its wings, takes off, and flies away while the skyline scrolls past. Then a new pigeon appears in front of a freshly generated city, and the loop starts again.

The whole thing is rendered procedurally with pure Python. There are no sprites, images, or external libraries. The bird is built from capsules, ellipses, and polygons, rasterised into terminal cells, and painted with 256-color ANSI escape codes.

## Features

- Procedurally drawn pigeon (body, head, beak, eye, legs, layered wing feathers)
- Full animation cycle: sleeping, waking, wing unfolding, take-off, cruising, flying off-screen
- Scrolling parallax city skyline with randomly flickering windows
- A new city is generated each loop
- Binary (`0`/`1`) "matrix" texture on the bird and buildings
- Adapts to your terminal size and re-renders if you resize the window
- Zero dependencies

## Requirements

- Python 3.6 or newer
- A terminal that supports 256-color ANSI escape codes (most modern terminals do)
- A terminal window of at least roughly 100x34 for the best result (it scales to smaller sizes)

See [`requirements.txt`](requirements.txt). There is nothing to `pip install`.


### Platform notes

- **macOS / Linux:** works in any standard terminal.
- **Windows:** use Windows Terminal or a recent PowerShell/CMD console. The script calls `os.system("")` to enable ANSI escape processing. Legacy consoles without ANSI support will show garbled output.

## Configuration

Tweak the constants at the top of `main.py` to change the animation.

| Constant | Default | What it does |
|---|---|---|
| `T_SIT` | `50` | Frames the pigeon sits calmly |
| `T_OPEN` | `30` | Frames spent unfolding wings and crouching |
| `PAUSE` | `25` | Frames of empty ledge before the next pigeon |
| `REVEAL` | `18` | Frames for the new pigeon to materialise |
| `BIRD_SCALE` | `0.50` | Size of the pigeon on screen |
| `T_CLIMB` | `40` | Frames of take-off and climb |
| `T_CRUISE` | `100` | Frames of level flight |
| `CRUISE_OX` | `14.0` | Horizontal position of the pigeon while cruising |
| `CRUISE_LIFT` | `-10.0` | Cruising height (negative is higher) |
| `SCROLL_V` | `1.4` | Skyline scroll speed (columns per frame) |
| `STRIP_EXTRA` | `420` | Extra skyline width that scrolls into view |

The animation targets about 20 frames per second (`time.sleep(0.05)` in `main()`).

## How it works

1. **Shapes:** `capsule`, `ellipse`, and `polygon` each return a bounding box plus an inside/outside test function and a color.
2. **Pigeon model:** `pigeon()` assembles those shapes into a bird, and `wing()` builds layered feathers with lag so the wingtips trail the wing root.
3. **Animation:** `pose(f)` returns the bird's pose for frame `f`: sitting, unfolding, then take-off, cruise, and exit.
4. **Scene:** `make_scene()` generates the skyline and ledge with a seeded RNG, and `flicker()` toggles random windows.
5. **Rendering:** `raster()` rasterises the shapes into a character grid, and `render()` composites bird, halo, and city into one ANSI-colored string that is drawn each frame.

## Project structure

```
.
├── main.py
├── requirements.txt
└── README.md
```

## License

Add a license of your choice (for example MIT) before publishing.
