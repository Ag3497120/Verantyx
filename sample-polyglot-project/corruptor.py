import os
import time
import hashlib
import glob

# Target directory
TARGET_DIR = "data/"

def corrupt_files():
    while True:
        # Find all .txt files in data/
        files = glob.glob(os.path.join(TARGET_DIR, "*.txt"))
        if files:
            # Pick a random file to corrupt one line
            target_file = files[0] 
            with open(target_file, 'r') as f:
                lines = f.readlines()
            
            if lines:
                # Corrupt the first line by replacing it with its hash
                line_to_corrupt = lines[0]
                corrupted_line = hashlib.sha256(line_to_corrupt.encode()).hexdigest() + "\n"
                lines[0] = corrupted_line
                
                with open(target_file, 'w') as f:
                    f.writelines(lines)
                print(f"Corrupted: {target_file}")
        
        # Wait for 60 seconds (reduced to 10 for testing purposes in this setup)
        time.sleep(10)

if __name__ == "__main__":
    corrupt_files()
