import subprocess


def run_command(command: str) -> str:
    """Executes a shell command and returns stdout. Returns stderr on failure."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
        return result.stdout if result.returncode == 0 else result.stderr
    except subprocess.TimeoutExpired:
        return 'Command timed out after 30 seconds.'
    except Exception:
        return ''
