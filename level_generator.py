import random
from collections import deque

from src.api import (
    ArtifactDefinition, CharacterDefinition, EnemyDefinition, GenerationFailure,
    LevelDefinition, LevelSpecification, Position, TerrainGeneratorContract,
)

# up, down, left, right as (row change, column change)
DIRECTIONS = [(-1, 0), (1, 0), (0, -1), (0, 1)]


class LevelGenerator:
    """Uses the terrain generator that is given to it."""

    def __init__(self, terrain_generator: TerrainGeneratorContract) -> None:
        self._terrain_generator = terrain_generator

    def generate_level(self, specification: LevelSpecification, seed: int) -> LevelDefinition:
        rng = random.Random(seed)

        for attempt in range(specification.max_attempts):
            terrain = self._terrain_generator.generate_terrain(
                specification.terrain_spec, seed + attempt
            )

            picked = self.pick_start_and_exit(terrain, specification, rng)
            if picked is None:
                continue
            start, exit_cell, route = picked

            # the route has (moves + 1) cells, and EXIT is one more action than moves
            if len(route) > specification.max_turns:
                continue
            if not self.shape_is_ok(terrain, specification, start, exit_cell, route):
                continue

            placed = self.place_things(terrain, specification, start, exit_cell, rng)
            if placed is None:
                continue
            artifacts, enemies = placed

            return LevelDefinition(
                level_id=specification.level_id,
                profile_id=specification.profile_id,
                seed=seed,
                terrain=terrain,
                start=start,
                exit=exit_cell,
                character=CharacterDefinition(specification.agent_id),
                artifacts=tuple(artifacts),
                enemies=tuple(enemies),
            )

        raise GenerationFailure("LevelGenerator", "no valid level found")

    def pick_start_and_exit(self, terrain, spec, rng):
        """Returns (start, exit, route) or None. The route is a list of cells."""
        floor = self.floor_cells(terrain)
        if len(floor) < 2:
            return None

        # start at the end of a path (a dead end) if there is one
        dead_ends = []
        for cell in floor:
            if len(self.floor_neighbors(terrain, cell)) == 1:
                dead_ends.append(cell)
        if len(dead_ends) > 0:
            start = rng.choice(dead_ends)
        else:
            start = rng.choice(floor)

        distance, parent = self.bfs(terrain, start, None)

        # the exit: a different cell, with a route length that is allowed
        fewest = max(1, spec.min_route_moves)
        allowed = []
        for cell in floor:
            if cell in distance and fewest <= distance[cell] <= spec.max_route_moves:
                allowed.append(cell)
        if len(allowed) == 0:
            return None

        # take the farthest one, so the start and exit are "opposite"
        farthest = 0
        for cell in allowed:
            if distance[cell] > farthest:
                farthest = distance[cell]
        far_cells = []
        for cell in allowed:
            if distance[cell] == farthest:
                far_cells.append(cell)
        exit_cell = rng.choice(far_cells)

        route = [exit_cell]
        while parent[route[-1]] is not None:
            route.append(parent[route[-1]])
        route.reverse()
        return start, exit_cell, route

    def shape_is_ok(self, terrain, spec, start, exit_cell, route):
        floor = self.floor_cells(terrain)

        # branch tiles = floor cells that are not on the route
        if len(floor) - len(route) < spec.min_branch_tiles:
            return False

        # dead ends = floor cells with one neighbor (start and exit do not count)
        dead_ends = 0
        for cell in floor:
            if cell == start or cell == exit_cell:
                continue
            if len(self.floor_neighbors(terrain, cell)) == 1:
                dead_ends = dead_ends + 1
        if dead_ends > spec.max_dead_end_tiles:
            return False

        if spec.require_alternate_path:
            # is there still a way to the exit if one step of the route is closed?
            found = False
            for i in range(len(route) - 1):
                closed = (route[i], route[i + 1])
                distance, parent = self.bfs(terrain, start, closed)
                if exit_cell in distance:
                    found = True
            if not found:
                return False
        return True

    def place_things(self, terrain, spec, start, exit_cell, rng):
        """Returns (artifacts, enemies) or None if there is no room."""
        free = []
        for cell in self.floor_cells(terrain):
            if not spec.allow_entities_on_endpoints and (cell == start or cell == exit_cell):
                continue
            free.append(cell)

        total = spec.artifact_count + spec.enemy_count
        if spec.allow_entity_overlap:
            if total > 0 and len(free) == 0:
                return None
            cells = []
            for i in range(total):
                cells.append(rng.choice(free))
        else:
            if len(free) < total:
                return None
            cells = rng.sample(free, total)

        artifacts = []
        for i in range(spec.artifact_count):
            value = rng.randint(spec.artifact_value_min, spec.artifact_value_max)
            artifacts.append(ArtifactDefinition("artifact_" + str(i + 1), cells[i], value))

        enemies = []
        for i in range(spec.enemy_count):
            penalty = rng.randint(spec.enemy_penalty_min, spec.enemy_penalty_max)
            cell = cells[spec.artifact_count + i]
            enemies.append(EnemyDefinition("enemy_" + str(i + 1), cell, penalty))

        return artifacts, enemies

    def floor_cells(self, terrain):
        cells = []
        for row in range(terrain.rows):
            for column in range(terrain.columns):
                cell = Position(row, column)
                if terrain.is_traversable(cell):
                    cells.append(cell)
        return cells

    def floor_neighbors(self, terrain, cell):
        neighbors = []
        for row_change, column_change in DIRECTIONS:
            neighbor = Position(cell.row + row_change, cell.column + column_change)
            if terrain.is_traversable(neighbor):
                neighbors.append(neighbor)
        return neighbors

    def bfs(self, terrain, start, closed_step):
        """Returns (moves to each cell, the cell we came from).
        closed_step = (a, b) is a step that may not be used, or None."""
        distance = {start: 0}
        parent = {start: None}
        queue = deque()
        queue.append(start)

        while len(queue) > 0:
            cell = queue.popleft()
            for neighbor in self.floor_neighbors(terrain, cell):
                if neighbor in distance:
                    continue
                if closed_step is not None:
                    if (cell, neighbor) == closed_step or (neighbor, cell) == closed_step:
                        continue
                distance[neighbor] = distance[cell] + 1
                parent[neighbor] = cell
                queue.append(neighbor)
        return distance, parent