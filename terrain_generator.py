import random

from src.api import GenerationFailure, Terrain, TerrainGenerationSpec, TerrainTopology

# up, down, left, right as (row change, column change)
DIRECTIONS = [(-1, 0), (1, 0), (0, -1), (0, 1)]


class TerrainGenerator:
    """Same inputs always give the same map, so nothing is stored here."""

    def __init__(self) -> None:
        pass

    def generate_terrain(self, specification: TerrainGenerationSpec, seed: int) -> Terrain:
        rng = random.Random(seed)  # same seed = same random numbers

        # grid[row][column], all walls at first
        grid = []
        for row in range(specification.rows):
            grid.append(["#"] * specification.columns)

        topology = specification.topology
        if topology == TerrainTopology.STRAIGHT_PATH:
            self.make_straight_path(grid, specification, rng)
        elif topology == TerrainTopology.BENT_PATH:
            self.make_bent_path(grid, specification, rng)
        elif topology == TerrainTopology.BRANCHING_TREE:
            self.grow_floor(grid, specification, rng, True)
        elif topology == TerrainTopology.GENERAL:
            self.grow_floor(grid, specification, rng, False)
        else:
            raise GenerationFailure("TerrainGenerator", "unknown topology")

        rows = []
        for line in grid:
            rows.append("".join(line))
        return Terrain(tuple(rows))

    def make_straight_path(self, grid, spec, rng):
        shortest = max(spec.min_open_tiles, 2)  # at least a start and an exit
        longest_across = min(spec.max_open_tiles, spec.columns)
        longest_down = min(spec.max_open_tiles, spec.rows)

        fits_across = shortest <= longest_across
        fits_down = shortest <= longest_down
        if not fits_across and not fits_down:
            raise GenerationFailure("TerrainGenerator", "no straight path fits")

        if fits_across and fits_down:
            across = rng.choice([True, False])
        else:
            across = fits_across

        if across:
            length = rng.randint(shortest, longest_across)
            row = rng.randrange(spec.rows)
            first = rng.randrange(spec.columns - length + 1)
            for i in range(length):
                grid[row][first + i] = "."
        else:
            length = rng.randint(shortest, longest_down)
            column = rng.randrange(spec.columns)
            first = rng.randrange(spec.rows - length + 1)
            for i in range(length):
                grid[first + i][column] = "."

    def make_bent_path(self, grid, spec, rng):
        # An L shape: one line across (wide cells) and one line down (tall cells).
        # They share the corner cell, so the floor count is wide + tall - 1.
        shapes = []
        for wide in range(2, spec.columns + 1):
            for tall in range(2, spec.rows + 1):
                if spec.min_open_tiles <= wide + tall - 1 <= spec.max_open_tiles:
                    shapes.append((wide, tall))
        if len(shapes) == 0:
            raise GenerationFailure("TerrainGenerator", "no bent path fits")

        wide, tall = rng.choice(shapes)
        top = rng.randrange(spec.rows - tall + 1)
        left = rng.randrange(spec.columns - wide + 1)

        # the corner can be at either end of each line
        corner_row = rng.choice([top, top + tall - 1])
        corner_column = rng.choice([left, left + wide - 1])

        for i in range(wide):
            grid[corner_row][left + i] = "."
        for i in range(tall):
            grid[top + i][corner_column] = "."

    def grow_floor(self, grid, spec, rng, is_tree):
        """Start with one floor cell and keep adding a cell next to the floor.

        is_tree = True: a new cell may touch the floor in only ONE place,
        so there are no loops. is_tree = False: loops are allowed.
        """
        fewest = spec.min_open_tiles
        if fewest < 2 <= spec.max_open_tiles:
            fewest = 2

        for attempt in range(spec.max_attempts):
            wanted = rng.randint(fewest, spec.max_open_tiles)
            cells = self.try_grow(spec, rng, wanted, is_tree)

            if len(cells) < fewest:
                continue  # got stuck, try again
            if is_tree and len(cells) >= 4 and not self.has_branch(cells):
                continue  # a tree should have a branch, try again

            for row, column in cells:
                grid[row][column] = "."
            return

        raise GenerationFailure("TerrainGenerator", "could not grow the terrain")

    def try_grow(self, spec, rng, wanted, is_tree):
        """Returns a list of (row, column) floor cells."""
        if wanted == 0:
            return []

        first = (rng.randrange(spec.rows), rng.randrange(spec.columns))
        cells = [first]
        floor = {first}

        while len(cells) < wanted:
            options = []
            for row in range(spec.rows):
                for column in range(spec.columns):
                    if (row, column) in floor:
                        continue
                    touching = self.count_touching(floor, row, column)
                    if touching == 1 or (touching > 1 and not is_tree):
                        options.append((row, column))
            if len(options) == 0:
                break  # nowhere left to grow

            new_cell = rng.choice(options)
            cells.append(new_cell)
            floor.add(new_cell)
        return cells

    def count_touching(self, floor, row, column):
        """How many of the 4 neighbors are floor."""
        count = 0
        for row_change, column_change in DIRECTIONS:
            if (row + row_change, column + column_change) in floor:
                count = count + 1
        return count

    def has_branch(self, cells):
        """True if some cell has 3 or more floor neighbors."""
        floor = set(cells)
        for row, column in cells:
            if self.count_touching(floor, row, column) >= 3:
                return True
        return False