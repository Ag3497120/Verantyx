import os
import re

def process_file(path):
    with open(path, 'r') as f:
        content = f.read()

    # Find occurrences of .buttonStyle(.plain) that don't have .contentShape(Rectangle()) right above them.
    # We will just replace all `.buttonStyle(.plain)` with `.contentShape(Rectangle())\n<indent>.buttonStyle(.plain)`
    # but first we need to make sure we don't duplicate it.

    lines = content.split('\n')
    changed = False
    
    for i in range(len(lines)):
        line = lines[i]
        if '.buttonStyle(.plain)' in line:
            # Check previous line
            prev_line = lines[i-1] if i > 0 else ""
            if '.contentShape(Rectangle())' not in prev_line and '.contentShape(Rectangle())' not in line:
                # Add .contentShape(Rectangle()) with same indentation
                indent = len(line) - len(line.lstrip())
                new_line = " " * indent + ".contentShape(Rectangle())"
                
                # If the line itself has closing brace `}.buttonStyle(.plain)`, insert before it
                if '}.buttonStyle(.plain)' in line:
                    lines[i] = line.replace('}.buttonStyle(.plain)', '}\n' + new_line + '\n' + " " * indent + '.buttonStyle(.plain)')
                else:
                    lines[i] = new_line + '\n' + line
                changed = True

    if changed:
        with open(path, 'w') as f:
            f.write('\n'.join(lines))
        print(f"Updated {path}")

for root, _, files in os.walk('.'):
    for f in files:
        if f.endswith('.swift'):
            process_file(os.path.join(root, f))
