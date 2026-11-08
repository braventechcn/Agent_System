"""六房间清扫：observe → decide → execute。"""

from itertools import product
from random import Random


ROOMS = ("A", "B", "C", "D", "E", "F")  # 一字排开的六个房间
MOVE_COST = 1   # 每移动到相邻房间花费 1
CLEAN_COST = 2  # 清扫一个脏房间花费 2


def observe(state, see_all=False):
    """基础策略只看当前房间；进阶策略能看到所有房间。"""
    # 观察当前房间位置和脏/干净状态
    position = state["position"]
    # 基础策略只能看到当前房间的脏/干净状态；进阶策略能看到所有房间的状态
    if see_all:
        return position, state["dirty"].copy()
    # 基础策略只能看到当前房间的脏/干净状态
    return position, state["dirty"][position]


def basic_agent(observation, known_clean):
    """清扫当前房间；否则探查最近的未知房间。"""
    # 基础策略只能根据当前房间的观察结果做决定
    position, is_dirty = observation
    # 当前房间脏时先清扫；这里只返回动作，房间状态不会立刻改变
    if is_dirty:
        return "CLEAN"

    # 观察到当前房间已干净，就把它记入已确认干净的房间
    known_clean.add(position)
    unknown = [room for room in ROOMS if room not in known_clean]
    # 所有房间都确认干净后，才允许结束
    if not unknown:
        return "DONE"

    # 选择距离最近的未知房间；距离相同时按 A 到 F 的顺序选择
    here = ROOMS.index(position)
    target = min(unknown, key=lambda room: abs(ROOMS.index(room) - here))
    # 每次只能移动到左边或右边的相邻房间
    return "RIGHT" if ROOMS.index(target) > here else "LEFT"


def optimal_agent(observation):
    """已知全部房间状态时，选择移动成本最低的路线。"""
    # 进阶策略能直接看到每个房间是否脏
    position, rooms = observation
    # 已经站在脏房间里，先清扫，不需要之后再折返
    if rooms[position]:
        return "CLEAN"

    # 将脏房间转换成位置序号，便于计算路线长度
    dirty = [ROOMS.index(room) for room in ROOMS if rooms[room]]
    # 没有脏房间时立即结束，不再做无谓的移动
    if not dirty:
        return "DONE"

    here, left, right = ROOMS.index(position), min(dirty), max(dirty)
    # 所有脏房间都在 left 和 right 之间；比较先去左端或先去右端
    # 清扫次数固定，因此移动距离更短的路线，总成本也更低
    left_first = abs(here - left) + (right - left)
    right_first = abs(here - right) + (right - left)
    target = left if left_first <= right_first else right
    # 朝选中的一端移动一步；下一轮会重新观察和决策
    return "LEFT" if target < here else "RIGHT"


def execute(state, action):
    """只有环境执行动作时，房间状态才会改变。返回本次成本。"""
    here = ROOMS.index(state["position"])
    # CLEAN 只能用于当前的脏房间，清扫后把它改为干净
    if action == "CLEAN" and state["dirty"][state["position"]]:
        state["dirty"][state["position"]] = False
        return CLEAN_COST
    # 左移时不能越过 A；右移时不能越过 F
    if action == "LEFT" and here > 0:
        state["position"] = ROOMS[here - 1]
        return MOVE_COST
    if action == "RIGHT" and here < len(ROOMS) - 1:
        state["position"] = ROOMS[here + 1]
        return MOVE_COST
    # 只有所有房间都干净时，DONE 才是合法动作
    if action == "DONE" and not any(state["dirty"].values()):
        state["done"] = True
        return 0
    # 其他情况（如越界、重复清扫、提前结束）都作为非法动作处理
    raise ValueError(f"非法动作: {action}，当前房间: {state['position']}")


def run(start, dirty, strategy, max_steps=3 * len(ROOMS)):
    # 创建独立的环境状态；复制 dirty，避免修改传入的初始状态
    state = {
        "position": start,
        "dirty": dirty.copy(),  # 这里的 dirty 包含所有房间的脏/干净状态
        "done": False
        }
    # 基础策略需要记住已确认干净的房间，避免重复探查
    known_clean = set()
    # 记录动作序列和总成本
    actions, cost = [], 0
    # 在有限步数内执行清扫任务，避免无限循环
    for _ in range(max_steps):
        # Step 1: 观察环境
        observation = observe(state, see_all=(strategy == "optimal"))
        # Step 2: 决策动作
        action = (optimal_agent(observation) if strategy == "optimal"
                  else basic_agent(observation, known_clean))
        # Step 3: 执行动作
        cost += execute(state, action)
        # 保存动作顺序，方便最后展示和比较两种策略
        actions.append(action)
        # 环境确认 DONE 合法后，本轮实验才算完成
        if state["done"]:
            return cost, actions
    # 超过步数限制仍未结束，就认为策略可能陷入循环
    raise AssertionError(f"It took more than {max_steps} steps, maybe a loop: {actions}")


def verify(trials=100):
    """默认从 384 种初始情况中随机抽取 100 种，不重复。"""
    # 六个起点 × 每个房间脏/干净两种状态，共 6 × 2⁶ = 384 组
    all_cases = [
        (start, states)
        for start in ROOMS
        for states in product((False, True), repeat=len(ROOMS))
    ]
    basic_cost = optimal_cost = 0
    # 固定随机种子，保证每次运行都抽到同样的样本，便于复现
    for start, states in Random(42).sample(all_cases, trials):
        dirty = dict(zip(ROOMS, states))
        # 用相同的起点和房间状态，分别运行两种策略
        cost1, actions1 = run(start, dirty, "basic")
        cost2, actions2 = run(start, dirty, "optimal")

        # 在一条直线上清扫所有脏房间，至少要走到最左和最右的脏房间。
        dirty_positions = [i for i, is_dirty in enumerate(states) if is_dirty]
        moves = 0
        if dirty_positions:
            here = ROOMS.index(start)
            left, right = min(dirty_positions), max(dirty_positions)
            # 两端之间的距离必须走完；先到较近的一端可减少起始路程
            moves = min(abs(here - left), abs(here - right)) + right - left
        # 理论最低成本 = 最少移动次数 × 移动成本 + 脏房间数 × 清扫成本
        minimum_cost = moves * MOVE_COST + len(dirty_positions) * CLEAN_COST

        # DONE 表示环境确认全部清扫完成；run() 同时限制了最大步数
        assert actions1[-1] == actions2[-1] == "DONE"
        # 检查进阶策略达到理论最低成本，基础策略不会比它更低
        assert cost2 == minimum_cost, (start, dirty, cost2, minimum_cost)
        assert cost1 >= cost2, (start, dirty, cost1, cost2)
        # 累计成本，用于最后计算平均值
        basic_cost += cost1
        optimal_cost += cost2

    print(f"随机抽取的 {trials} 组状态全部通过：清扫完成、动作合法、步数达标、进阶成本最低")
    print(f"基础策略平均成本: {basic_cost / trials:.2f}")
    print(f"进阶策略平均成本: {optimal_cost / trials:.2f}")


if __name__ == "__main__":
    # 从 C 出发：A/B/D 干净，C/E/F 脏。基础策略会先向左探查。
    start = "C"
    example = {
        "A": False,  # 房间 A 干净
        "B": False,  # 房间 B 干净
        "C": True,   # 房间 C 脏
        "D": False,  # 房间 D 干净
        "E": True,   # 房间 E 脏
        "F": True    # 房间 F 脏
    }

    # 有两种策略
    # 1. 基础策略：只能看到当前房间状态
    # 2. 进阶策略：能看到所有房间状态
    basic_cost, basic_actions = run(start, example, "basic")
    print(f"basic: {' → '.join(basic_actions)}，成本 {basic_cost}")

    optimal_cost, optimal_actions = run(start, example, "optimal")
    print(f"optimal: {' → '.join(optimal_actions)}，成本 {optimal_cost}")
    verify()
