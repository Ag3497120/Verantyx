#!/bin/bash
export WINEPREFIX="$HOME/Verantyx_VR_Drive/SteamVR_Prefix"
export PATH="/Applications/Game Porting Toolkit.app/Contents/Resources/wine/bin:$PATH"
export DYLD_FALLBACK_LIBRARY_PATH="/Applications/Game Porting Toolkit.app/Contents/Resources/wine/lib:/usr/lib"
export WINEESYNC=1
wine64 "$@"
