from pathlib import Path


def symlinks_supported(tmp_path: Path) -> bool:
    try:
        target = tmp_path / "target"
        target.mkdir()
        link = tmp_path / "link"
        link.symlink_to(target)
        return True
    except (OSError, NotImplementedError):
        return False
