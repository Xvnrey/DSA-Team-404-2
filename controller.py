
from collections import deque

from src.api import Position, WorldAction, WorldActionType

# each move with its (row change, column change)
MOVES = [
    (WorldActionType.MOVE_NORTH, -1, 0),
    (WorldActionType.MOVE_SOUTH, 1, 0),
    (WorldActionType.MOVE_WEST, 0, -1),
    (WorldActionType.MOVE_EAST, 0, 1),
]


class AgentController:
    """A new controller is made for each run."""

    def __init__(self) -> None:
        pass

    def choose_action(self, state, agent_id: str) -> WorldAction:
        here = state.agent_position
        exit_cell = state.exit_position

        # the cheapest way to the exit, without any reward
        direct = self.find_route(state, here, exit_cell)
        if direct is None:
            return WorldAction.wait()

        # is a reward worth it?
        best = self.pick_reward(state, here, direct)

        if best is not None:
            reward, route = best
            if reward.position == here:
                return WorldAction(WorldActionType.COLLECT, target_id=reward.artifact_id)
        else:
            if here == exit_cell:
                return WorldAction(WorldActionType.EXIT)
            route = direct

        action = self.take_step(state, route[0])
        return self.keep_safe(state, action)

    # ----- rewards -----

    def pick_reward(self, state, here, direct):
        """Return (reward, route to it) for the best reward, or None."""
        if WorldActionType.COLLECT not in state.allowed_actions:
            return None

        limit = state.max_turns
        if state.deadline_turn is not None:
            limit = min(limit, state.deadline_turn)

        spent = self.cost_so_far(state)
        direct_cost = direct[1]
        lost_direct = self.points_lost(state, spent + direct_cost + 1)  # +1 for EXIT

        best = None
        best_profit = -1
        for reward in state.level.artifacts:
            if reward.artifact_id in state.collected_artifact_ids:
                continue

            to_reward = self.find_route(state, here, reward.position)
            to_exit = self.find_route(state, reward.position, state.exit_position)
            if to_reward is None or to_exit is None:
                continue

            # not enough actions left for the detour?
            actions = to_reward[2] + 1 + to_exit[2] + 1
            if state.turn + actions > limit:
                continue

            total_cost = spent + to_reward[1] + 1 + to_exit[1] + 1  # +1 COLLECT, +1 EXIT
            lost = self.points_lost(state, total_cost)
            profit = reward.value - (lost - lost_direct)

            if profit >= 0 and profit > best_profit:
                best = (reward, to_reward)
                best_profit = profit
        return best

    def cost_so_far(self, state):
        """Actions used so far plus the penalties already paid."""
        total = state.turn
        for enemy in state.level.enemies:
            if enemy.enemy_id in state.defeated_enemy_ids:
                total = total + enemy.encounter_penalty
        return total

    def points_lost(self, state, total_cost):
        """Points taken away for a total cost (only the part above the baseline)."""
        extra = total_cost - state.baseline_cost
        if extra < 0:
            extra = 0
        return state.deduction_rate * extra

    # ----- routes -----

    def find_route(self, state, start, goal):
        """Return (path, cost, actions) or None.

        Two paths are tried: one that goes around the enemies and one that goes
        through them. The cheaper one is used.
        """
        enemies = self.enemies_on_map(state)

        options = []
        path = self.bfs(state, start, goal, enemies, False)
        if path is not None:
            options.append(path)
        if len(enemies) > 0 and WorldActionType.ENGAGE in state.allowed_actions:
            path = self.bfs(state, start, goal, enemies, True)
            if path is not None:
                options.append(path)

        best = None
        for path in options:
            moves = len(path) - 1
            cost = moves
            actions = moves
            for cell in path[1:]:
                if cell in enemies:
                    cost = cost + 1 + enemies[cell].encounter_penalty  # ENGAGE + penalty
                    actions = actions + 1                              # ENGAGE
            if best is None or cost < best[1]:
                best = (path, cost, actions)
        return best

    def bfs(self, state, start, goal, enemies, can_pass_enemies):
        """Breadth-first search with a queue. Returns the list of cells from start to goal."""
        parent = {start: None}
        queue = deque()
        queue.append(start)

        while len(queue) > 0:
            cell = queue.popleft()
            if cell == goal:
                break
            for move, row_change, column_change in MOVES:
                neighbor = Position(cell.row + row_change, cell.column + column_change)
                if neighbor in parent:
                    continue
                if not state.is_traversable(neighbor):
                    continue
                if neighbor in enemies and not can_pass_enemies:
                    continue
                parent[neighbor] = cell
                queue.append(neighbor)

        if goal not in parent:
            return None

        path = [goal]
        while parent[path[-1]] is not None:
            path.append(parent[path[-1]])
        path.reverse()
        return path

    def enemies_on_map(self, state):
        """A dictionary of cell -> enemy for the standing enemies that are still alive."""
        patrol_ids = []
        for patrol in state.level.patrols:
            patrol_ids.append(patrol.enemy_id)

        enemies = {}
        for enemy in state.level.enemies:
            if enemy.enemy_id in state.defeated_enemy_ids:
                continue
            if enemy.enemy_id in patrol_ids:
                continue
            enemies[enemy.position] = enemy
        return enemies

    # ----- one step -----

    def take_step(self, state, path):
        """Do the first step of the path: ENGAGE an enemy in the way, or move."""
        here = path[0]
        next_cell = path[1]

        enemies = self.enemies_on_map(state)
        if next_cell in enemies:
            return WorldAction(WorldActionType.ENGAGE, target_id=enemies[next_cell].enemy_id)

        for move, row_change, column_change in MOVES:
            if Position(here.row + row_change, here.column + column_change) == next_cell:
                return WorldAction(move)

    # ----- moving enemies (patrols) -----

    def patrol_cells(self, state):
        """Cells where a patrol is now or will be after the next action."""
        cells = set()
        for patrol in state.level.patrols:
            for seen in state.enemy_observations:
                if seen.enemy_id == patrol.enemy_id and seen.position is not None:
                    cells.add(seen.position)
                    if seen.phase is not None:
                        cells.add(patrol.positions[(seen.phase + 1) % patrol.period])
        return cells

    def cell_after(self, here, action):
        """The cell we stand on after the action."""
        for move, row_change, column_change in MOVES:
            if action.action_type == move:
                return Position(here.row + row_change, here.column + column_change)
        return here

    def keep_safe(self, state, action):
        """If a patrol would hit us, wait or step aside instead."""
        if action.action_type == WorldActionType.EXIT:
            return action
        danger = self.patrol_cells(state)
        here = state.agent_position
        if self.cell_after(here, action) not in danger:
            return action

        enemies = self.enemies_on_map(state)
        options = [WorldAction.wait()]
        for move, row_change, column_change in MOVES:
            options.append(WorldAction(move))
        for option in options:
            cell = self.cell_after(here, option)
            if cell in danger:
                continue
            if option.action_type != WorldActionType.WAIT:
                if not state.is_traversable(cell) or cell in enemies:
                    continue
            return option
        return action