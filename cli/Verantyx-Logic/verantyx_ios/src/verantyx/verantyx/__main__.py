import os

os.environ.setdefault("LC_ALL", "C")
os.environ.setdefault("LANG", "C")

from verantyx.app import main

if __name__ == '__main__':
    main().main_loop()
