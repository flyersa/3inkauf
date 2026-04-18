"""Color palette used for auto-assigning distinct colors to users.

Goals:
- Visually distinct at small chip sizes (legend dots, item borders).
- Accessible contrast against white background.
- Covers enough hues that collisions are unlikely for typical household groups.
"""
import random

# Historic "app blue" — kept first so its hue is still represented in the palette.
DEFAULT_COLOR = "#4A90D9"

USER_COLOR_PALETTE = [
    "#4A90D9",  # blue
    "#E74C3C",  # red
    "#2ECC71",  # green
    "#F39C12",  # orange
    "#9B59B6",  # purple
    "#1ABC9C",  # teal
    "#E67E22",  # carrot
    "#16A085",  # dark teal
    "#D35400",  # burnt orange
    "#8E44AD",  # dark purple
    "#2980B9",  # dark blue
    "#C0392B",  # dark red
    "#F1C40F",  # yellow
    "#27AE60",  # forest green
    "#34495E",  # slate
]


def random_user_color(avoid: list[str] | None = None) -> str:
    """Pick a random palette colour, avoiding the ones in `avoid` if possible."""
    avoid_set = {c.lower() for c in (avoid or []) if c}
    pool = [c for c in USER_COLOR_PALETTE if c.lower() not in avoid_set]
    if not pool:
        pool = USER_COLOR_PALETTE
    return random.choice(pool)
