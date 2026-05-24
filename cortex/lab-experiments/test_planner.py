#!/usr/bin/env python3
import sys, os
ARC_DIR = "/Users/motonishikoudai/verantyx_v6/arc-agi-3/ARC-AGI-3-Agents"
sys.path.insert(0, ARC_DIR)
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(ARC_DIR, ".env"))

import importlib.util
def load_cross_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

sim_mod = load_cross_module('simulator', os.path.join(ARC_DIR, 'agents/cross_engine/simulator.py'))
CrossWorld = sim_mod.CrossWorld

sys.path.insert(0, "/Users/motonishikoudai/verantyx-cli/src/verantyx/cross_engine")
from planner import AStarPlanner

try:
    from arc_agi import Arcade
    arcade = Arcade()
    scorecard = arcade.create_scorecard()
    env = arcade.make("ls20", scorecard_id=scorecard)
    frame = env.reset()
    grid_data = getattr(frame, "grid", [])
    if not grid_data and hasattr(frame, 'frame') and hasattr(frame.frame, '__getitem__'):
        grid_data = frame.frame[0].tolist()

    world = CrossWorld(grid_data)
    planner = AStarPlanner(grid_data)
    p_pos = list(world.player_pos)
    t_pos = list(world.lock_pos)
    blocked_colors = [5] # As in the Gemini rule
    
    # Check if a path can be found without blocked_colors
    act2 = planner.get_next_action(p_pos, t_pos, [])
    print(f"Path ignoring obstacles => Action: {act2}")

    print("Colors around player:")
    y, x = p_pos
    for dy, dx in [(-1,0), (1,0), (0,-1), (0,1)]:
        if 0 <= y+dy < len(grid_data) and 0 <= x+dx < len(grid_data[0]):
            print(f"Dir({dy},{dx}) => Color: {grid_data[y+dy][x+dx]}")

except Exception as e:
    print("Error:", e)
