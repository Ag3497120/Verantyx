with open('/Users/motonishikoudai/verantyx-cli/verantyx-browser/crates/vx-browser/src/stealth_bridge.rs', 'r') as f:
    lines = f.readlines()

new_lines = []
skip = False
for line in lines:
    if "if let Some(rl) = tap_run_loop" in line:
        skip = True
        continue
    if skip and "rl.stop();" in line:
        continue
    if skip and "}" in line:
        skip = False
        continue
    new_lines.append(line)

with open('/Users/motonishikoudai/verantyx-cli/verantyx-browser/crates/vx-browser/src/stealth_bridge.rs', 'w') as f:
    f.writelines(new_lines)
