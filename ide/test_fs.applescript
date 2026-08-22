tell application "Safari" to activate
tell application "System Events"
    tell process "Safari"
        if not (value of attribute "AXFullScreen" of window 1) then
            set value of attribute "AXFullScreen" of window 1 to true
        end if
    end tell
end tell
