"""Attach the subprocess's controlling terminal, then replace it with the shell.

Launched with a fresh POSIX session and a slave PTY on stdin/stdout/stderr.
Kept separate so the threaded web server never uses preexec_fn or fork callbacks.
"""
import fcntl
import os
import sys
import termios

if __name__ == '__main__':
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)
    shell = sys.argv[1]
    os.execve(shell, [shell, '-i'], os.environ)
