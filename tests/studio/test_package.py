from scripts import package_studio
from zipfile import ZipFile


def test_package_collects_only_local_bundled_reference_images(tmp_path):
    character = tmp_path / 'studio' / 'builtin' / 'character'
    scene = tmp_path / 'studio' / 'builtin' / 'scene'
    character.mkdir(parents=True)
    scene.mkdir(parents=True)
    actor = character / 'actor.webp'
    room = scene / 'room.webp'
    actor.write_bytes(b'actor')
    room.write_bytes(b'room')
    (character / 'notes.txt').write_text('not an image')
    (scene / 'link.webp').symlink_to(actor)

    assert hasattr(package_studio, 'bundled_files'), 'packager must include built-in images'
    assert package_studio.bundled_files(tmp_path) == {actor, room}


def test_windows_package_has_chinese_one_click_entry(tmp_path):
    output = tmp_path / 'studio.zip'
    package_studio.package(output_path=output)
    with ZipFile(output) as archive:
        assert 'videoX/一键启动.cmd' in archive.namelist()
        assert 'videoX/使用说明.txt' in archive.namelist()


def test_package_includes_explicit_untracked_language_modules_only(tmp_path, monkeypatch):
    import studio.frontend_build
    root = tmp_path / 'source'
    root.mkdir()
    tracked = ['studio/frontend_build.py', 'studio/app.py', 'Start Studio.cmd',
               'scripts/start-studio.ps1', 'requirements-studio.txt']
    for name in tracked + ['studio/languages.py', 'studio/language_check.py',
                           'studio/not_approved.py', '一键启动.cmd', '使用说明.txt',
                           'studio-web/dist/index.html', 'scripts/package_studio.py',
                           'docs/multimarket-ugc-spec.md',
                           'docs/superpowers/plans/2026-11-09-multimarket-ugc.md']:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('test', encoding='utf-8')
    monkeypatch.setattr(package_studio, 'ROOT', root)
    monkeypatch.setattr(package_studio.subprocess, 'check_output', lambda *a, **kw: ('\0'.join(tracked) + '\0').encode())
    monkeypatch.setattr(package_studio.subprocess, 'run', lambda *a, **kw: None)
    monkeypatch.setattr(package_studio.shutil, 'which', lambda _: '/mock/pnpm')
    monkeypatch.setattr(studio.frontend_build, 'fingerprint', lambda _: 'test')
    output = tmp_path / 'package.zip'
    package_studio.package(output_path=output)
    with ZipFile(output) as archive:
        names = set(archive.namelist())
    assert {'videoX/studio/languages.py', 'videoX/studio/language_check.py'} <= names
    assert {'videoX/docs/multimarket-ugc-spec.md', 'videoX/docs/superpowers/plans/2026-11-09-multimarket-ugc.md'} <= names
    assert 'videoX/studio/not_approved.py' not in names
