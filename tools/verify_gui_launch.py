"""Run the startup smoke check on a fresh profile and check the reported version."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if not __package__:
    sys.path.insert(0, str(ROOT))

from tools.release_inputs import read_version
from utils.startup_check import PROFILE_ENV, REPORT_NAME


def validate_startup_report(report, expected_version):
    if (not isinstance(report, dict)
            or report.get('version') != expected_version
            or report.get('main_window') is not True
            or type(report.get('tool_count')) is not int or report['tool_count'] < 1
            or any(not isinstance(report.get(key), str) or not report[key].strip()
                   for key in ('title', 'tk'))):
        raise ValueError(f'The startup report does not show a working window at v{expected_version}')
    return report


def run_startup_check(command, expected_version):
    command = list(command)
    if not command:
        raise ValueError('Provide an application command')
    if Path(command[0]).name.lower() in {'wine', 'wine64'} and not os.environ.get('WINEPREFIX'):
        raise ValueError('Set WINEPREFIX to an isolated Wine prefix first')
    command = [str(Path(part).resolve()) if Path(part).is_file() else str(part) for part in command]
    with tempfile.TemporaryDirectory(prefix='gurps-launch-') as directory:
        profile = str(Path(directory) / 'profile')
        env = {**os.environ, PROFILE_ENV: profile}
        env['APPDATA' if os.name == 'nt' else 'XDG_DATA_HOME'] = profile
        subprocess.run([*command, '--startup-check'], cwd=directory, env=env, check=True, timeout=60)
        try:
            report = json.loads((Path(directory) / REPORT_NAME).read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise ValueError('The application did not produce a startup report') from exc
    return validate_startup_report(report, expected_version)


def main():
    if not sys.argv[1:]:
        print('Usage: python tools/verify_gui_launch.py <application command>', file=sys.stderr)
        return 2
    try:
        result = run_startup_check(sys.argv[1:], read_version(ROOT))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f'Startup check failed: {exc}', file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
