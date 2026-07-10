import os
import runpy
import subprocess
import sys
import traceback


def _append_log_header(log_file):
    log_file.write("\n")
    log_file.write("==== Ping Tuckz GUI launch ====\n")
    log_file.flush()


def _open_error_window(log_path, exit_code=None):
    command = (
        "title Ping Tuckz launch error"
        " & echo Ping Tuckz could not start or exited unexpectedly."
    )
    if exit_code is not None:
        command += f" & echo Exit code: {exit_code}."
    command += (
        f" & echo Crash log: \"{log_path}\""
        " & echo."
        f" & type \"{log_path}\""
        " & echo."
        " & pause"
    )
    subprocess.Popen(
        ["cmd.exe", "/k", command],
        creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
    )


def main():
    if len(sys.argv) != 3:
        print("Usage: launch-gui.py <gui-script> <log-path>", file=sys.stderr)
        return 2

    script_path = os.path.abspath(sys.argv[1])
    log_path = os.path.abspath(sys.argv[2])
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    with open(log_path, "a", encoding="utf-8") as log_file:
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        original_argv = sys.argv
        sys.stdout = log_file
        sys.stderr = log_file
        sys.argv = [script_path]
        _append_log_header(log_file)
        try:
            runpy.run_path(script_path, run_name="__main__")
            return 0
        except SystemExit as exc:
            if exc.code is None:
                code = 0
            elif isinstance(exc.code, int):
                code = exc.code
            else:
                print(exc.code)
                code = 1
            if code:
                print(f"GUI exited with error code {code}.")
                log_file.flush()
                _open_error_window(log_path, code)
            return code
        except Exception:
            traceback.print_exc()
            log_file.flush()
            _open_error_window(log_path)
            return 1
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            sys.argv = original_argv


if __name__ == "__main__":
    raise SystemExit(main())
