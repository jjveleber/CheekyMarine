#!/usr/bin/env bash
# Poke a running demo app by hand to find coordinates (window coordinates at 1280x800).
#   bash x.sh tap X Y | hold X Y SECS | drag X1 Y1 X2 Y2 | shot PATH.png
# Only the app the engine started (it listens on the demo socket): other sessions run the same app.
PID=$(ps -eo pid,comm,args | awk -v s="/run/user/$(id -u)/cm-demo-n2k.sock" '$2=="cheekyplotter" && index($0, s) {print $1; exit}')
[ -n "$PID" ] || { echo "no demo cheekyplotter running (start one with engine.py ... rehearse, or App.launch)" >&2; exit 1; }
W=$(for w in $(xdotool search --onlyvisible --pid "$PID"); do
      xdotool getwindowgeometry "$w" | grep -q 1280x800 && echo "$w"; done | head -1)
[ -n "$W" ] || { echo "demo app $PID has no 1280x800 window" >&2; exit 1; }
case $1 in
  tap)  xdotool mousemove --window "$W" "$2" "$3" click 1 ;;
  hold) xdotool mousemove --window "$W" "$2" "$3" mousedown 1; sleep "$4"; xdotool mouseup 1 ;;
  drag) xdotool mousemove --window "$W" "$2" "$3" mousedown 1
        for i in $(seq 1 12); do
          xdotool mousemove --window "$W" $(( $2 + ($4 - $2) * i / 12 )) $(( $3 + ($5 - $3) * i / 12 )); sleep 0.04
        done
        xdotool mouseup 1 ;;
  shot) ffmpeg -v error -y -f x11grab -window_id "$W" -i :0 -frames:v 1 -vf scale=640:-1 "$2" ;;
  *)    echo "usage: x.sh tap X Y | hold X Y SECS | drag X1 Y1 X2 Y2 | shot PATH" >&2; exit 2 ;;
esac
