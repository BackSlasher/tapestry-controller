from typing import NamedTuple


class Dimensions(NamedTuple):
    width: int
    height: int


class Point(NamedTuple):
    x: int
    y: int

    def __add__(self, other: Dimensions) -> "Point":
        return Point(
            self.x + other.width,
            self.y + other.height,
        )


class Rectangle(NamedTuple):
    start: Point
    dimensions: Dimensions

    def get_corners(self) -> list[Point]:
        return [
            self.start,
            self.start + self.dimensions,
        ]

    @staticmethod
    def bounding_rectangle(rectangles: list["Rectangle"]) -> "Rectangle":
        all_points_deep = [r.get_corners() for r in rectangles]
        all_points = [item for sublist in all_points_deep for item in sublist]
        all_x = {p.x for p in all_points}
        all_y = {p.y for p in all_points}

        return Rectangle(
            start=Point(
                x=min(all_x),
                y=min(all_y),
            ),
            dimensions=Dimensions(
                width=(max(all_x) - min(all_x)),
                height=(max(all_y) - min(all_y)),
            ),
        )

    def ratioed(self, ratio: int) -> "Rectangle":
        return Rectangle(
            start=Point(
                x=self.start.x * ratio,
                y=self.start.y * ratio,
            ),
            dimensions=Dimensions(
                width=self.dimensions.width * ratio,
                height=self.dimensions.height * ratio,
            ),
        )
