import json
import sys

# We don't have the stdout saved in a file, but I can check the last command's output if I rerun it with a pipe or just assume success if returncode was 0.
# Actually, I'll just rerun it and pipe to a file to be sure.
