"""Build a portable ZIP with the approved built-in references, never runtime data or credentials."""
from pathlib import Path
import subprocess
import sys
import zipfile
import shutil

ROOT = Path(__file__).resolve().parent.parent


def bundled_files(root: Path):
    files = set()
    for role in ('character', 'scene'):
        folder = Path(root) / 'studio' / 'builtin' / role
        if folder.is_dir():
            files.update(
                path for path in folder.iterdir()
                if path.is_file() and not path.is_symlink() and path.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp')
            )
    return files


def package(output_path: Path | None = None):
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    required = {'studio/frontend_build.py', 'studio/app.py', 'Start Studio.cmd',
                'scripts/start-studio.ps1', 'requirements-studio.txt'}
    missing = required - set(tracked)
    if missing:
        raise SystemExit(f'Stage required source files before packaging: {sorted(missing)}')
    pnpm = shutil.which('pnpm')
    if not pnpm:
        raise SystemExit('Packaging requires pnpm and installed studio-web dependencies.')
    subprocess.run([pnpm, 'build'], cwd=ROOT / 'studio-web', check=True)
    web_dist = ROOT / 'studio-web' / 'dist'
    if not (web_dist / 'index.html').is_file():
        raise SystemExit('Build studio-web first: pnpm build')
    sys.path.insert(0, str(ROOT))
    from studio.frontend_build import fingerprint
    (web_dist / 'inputs.sha256').write_text(fingerprint(ROOT / 'studio-web'), encoding='ascii')
    output = Path(output_path) if output_path is not None else ROOT.parent / 'videoX-Brazil-UGC-Windows.zip'
    files = {ROOT / name for name in tracked if name}
    files.update(p for p in web_dist.rglob('*') if p.is_file())
    files.update(bundled_files(ROOT))
    # Include this build helper even before git staging; no broad untracked-file scan.
    files.add(ROOT / 'scripts' / 'package_studio.py')
    # These runtime modules are included even before staging, without scanning
    # other untracked files. Missing modules must fail the build, not produce
    # a ZIP that fails at startup.
    for name in ('studio/languages.py', 'studio/language_check.py'):
        source = ROOT / name
        if not source.is_file() or source.is_symlink():
            raise SystemExit(f'Missing required runtime module: {name}')
        files.add(source)
    # README links these specific implementation documents, including before staging.
    for name in ('docs/multimarket-ugc-spec.md', 'docs/superpowers/plans/2026-11-09-multimarket-ugc.md'):
        source = ROOT / name
        if not source.is_file() or source.is_symlink():
            raise SystemExit(f'Missing required documentation: {name}')
        files.add(source)
    # The localized entry point is required even before it has been staged.
    launcher = ROOT / '一键启动.cmd'
    if not launcher.is_file():
        raise SystemExit('Missing Chinese Windows launcher: 一键启动.cmd')
    files.add(launcher)
    quickstart = ROOT / '使用说明.txt'
    if not quickstart.is_file():
        raise SystemExit('Missing Chinese quickstart: 使用说明.txt')
    files.add(quickstart)
    live_report = ROOT / 'docs/live-deepseek-wavespeed-integration-2026-09-14.md'
    if live_report.is_file():
        files.add(live_report)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            relative = path.relative_to(ROOT)
            if path.is_symlink() or not path.is_file():
                continue
            if any(part in {'.git', '.studio', '.venv', 'node_modules', '__pycache__'} for part in relative.parts):
                continue
            if (relative.name.startswith('.env') and relative.name != '.env.example') or relative.name.endswith('.pyc'):
                continue
            archive.write(path, Path('videoX') / relative)
    print(f'{output}\n{output.stat().st_size / (1024*1024):.1f} MiB')


if __name__ == '__main__':
    package()
