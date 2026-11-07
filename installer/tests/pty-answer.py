"""pty-answer.py ANSWER... -- COMMAND...: run COMMAND on a pty and type the next ANSWER each time
the output shows a "[y/N]" prompt (so no answer is consumed early). Copies the output to stdout and
exits with COMMAND's status; 124 after 300 s."""
import os
import pty
import select
import sys
import time

i = sys.argv.index("--")
answers, cmd = sys.argv[1:i], sys.argv[i + 1:]
pid, fd = pty.fork()
if pid == 0:
    os.execvp(cmd[0], cmd)
buf = b""
deadline = time.time() + 300
while time.time() < deadline:
    r, _, _ = select.select([fd], [], [], 1)
    if r:
        try:
            data = os.read(fd, 4096)
        except OSError:
            break
        if not data:
            break
        sys.stdout.buffer.write(data)
        sys.stdout.flush()
        buf += data
        while b"[y/N]" in buf:
            buf = buf.split(b"[y/N]", 1)[1]
            os.write(fd, ((answers.pop(0) if answers else "n") + "\n").encode())
else:
    os.kill(pid, 9)
    sys.exit(124)
_, status = os.waitpid(pid, 0)
sys.exit(os.waitstatus_to_exitcode(status))
