from __future__ import annotations

from dataclasses import dataclass

from .models import GridPosition, PageSpec


@dataclass(frozen=True)
class PixelPosition:
    x: float
    y: float
    width: float
    height: float
    z: int
    tab_order: int


def grid_to_pixels(
    position: GridPosition,
    *,
    page_width: int,
    margin: int = 24,
    gap: int = 16,
    row_height: int = 48,
    index: int = 0,
) -> PixelPosition:
    usable_width = page_width - (2 * margin) - (11 * gap)
    column_width = usable_width / 12
    x = margin + position.column * (column_width + gap)
    y = margin + position.row * (row_height + gap)
    width = position.width * column_width + (position.width - 1) * gap
    height = position.height * row_height + (position.height - 1) * gap
    return PixelPosition(
        x=round(x, 3),
        y=round(y, 3),
        width=round(width, 3),
        height=round(height, 3),
        z=1000 + index,
        tab_order=1000 + index,
    )


def validate_page_layout(page: PageSpec) -> list[str]:
    errors: list[str] = []
    for index, visual in enumerate(page.visuals):
        pixel = grid_to_pixels(visual.position, page_width=page.width, index=index)
        if pixel.y + pixel.height > page.height - 24:
            errors.append(f"{visual.title}: visual extends below page boundary")

    for left_index, left in enumerate(page.visuals):
        a = left.position
        for right in page.visuals[left_index + 1:]:
            b = right.position
            separated = (
                a.column + a.width <= b.column
                or b.column + b.width <= a.column
                or a.row + a.height <= b.row
                or b.row + b.height <= a.row
            )
            if not separated:
                errors.append(f"{left.title} overlaps {right.title}")
    return errors
