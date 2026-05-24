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
    print("p_pos:", world.player_pos)
    print("t_pos:", world.lock_pos)
except Exception as e:
    print("Error:", e)
