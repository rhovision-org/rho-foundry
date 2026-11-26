# Enumerate the states, then compile the arithmetic

The first plate plots the exact 261 reachable pairs of held and issued counts in the 32-seat fixture with a hold limit of eight. The free count follows from the fixed total. The second plate shows the million-seat quota contract. The manager calls `fill_quota`, changing the counters to 750,000 free, 250,000 held and zero issued at revision 1.

The line over the bar marks the planned quantity. The counters change together when the operation commits. [Static storyboard](overview.png) · [Symbolic backend and benchmark](../SYMBOLIC.md)

Regenerate with Python, Pillow, fontconfig, Latin Modern Roman and Noto Sans.

```sh
python3 docs/motion/render.py
```

The command writes the GIF and the static PNG beside the renderer.
