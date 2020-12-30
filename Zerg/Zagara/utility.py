from all_imports_packages import *

def get_positions_around_unit(unit, min_range=0, max_range=500, step_size=1, location_amount=32):
    loc = unit.position.to2

    positions = []
    for alpha in range(location_amount):
        for distance in range(min_range, max_range + 1, step_size):
            positions.append(
                Point2(
                    (
                        loc.x + distance * math.cos(math.pi * 2 * alpha / location_amount),
                        loc.y + distance * math.sin(math.pi * 2 * alpha / location_amount)
                    )
                )
            )
    return positions


def get_closest_distance(locations, point):
    distances = []
    for loc in locations:
        distances.append(point.distance_to(loc))
    return min(distances)


def neighbors_4(position, distance=1):
    p = position
    d = distance
    return {Point2((p.x - d, p.y)), Point2((p.x + d, p.y)), Point2((p.x, p.y - d)), Point2((p.x, p.y + d))}


def neighbors_8(position, distance=1):
    p = position
    d = distance
    return neighbors_4(position, distance) | {
        Point2((p.x - d, p.y - d)),
        Point2((p.x - d, p.y + d)),
        Point2((p.x + d, p.y - d)),
        Point2((p.x + d, p.y + d)),
    }
