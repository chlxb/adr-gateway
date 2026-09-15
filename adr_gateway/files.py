"""Keep output files in one configured directory; preserve caller filenames."""
from pathlib import Path, PureWindowsPath
from uuid import uuid4
from urllib.parse import quote


def upstream_path(local: Path, adr_root: str | None) -> str:
    if not adr_root:
        return str(local)
    if PureWindowsPath(adr_root).drive:
        return str(PureWindowsPath(adr_root) / local.name)
    return str(Path(adr_root) / local.name)


def download_file(root: Path, name: str) -> Path:
    """Resolve a single public artifact name without accepting client directories."""
    if (not name or any(c in name for c in '/\\:')
            or any(ord(c) < 32 for c in name)
            or name.endswith((' ', '.'))
            or PureWindowsPath(name).suffix.lower() not in {'.tif', '.tiff', '.dcm', '.xml'}):
        raise FileNotFoundError(name)
    target = root / name
    if target.is_symlink() or target.resolve().parent != root.resolve() or not target.is_file():
        raise FileNotFoundError(name)
    return target


def capture_downloads(root: Path, film: Path) -> dict:
    result = {}
    for kind, name in (('film', film.name), ('ai', film.stem + '_ai.xml'),
                       ('humanReview', film.stem + '.xml')):
        try:
            target = download_file(root, name)
            result[kind] = {'filename': name, 'url': '/api/v1/files/' + quote(name, safe=''),
                            'sizeBytes': target.stat().st_size}
        except OSError:
            result[kind] = None
    return result


def capture_path(root: Path, supplied: str | None) -> Path:
    # Windows paths are accepted even when tests run on another platform.
    name = PureWindowsPath(supplied).name if supplied else f"film_{uuid4().hex}.tif"
    filename = PureWindowsPath(name)
    reserved = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
        prefix + digit for prefix in ("COM", "LPT") for digit in "123456789¹²³"}
    if (not name or filename.suffix.lower() not in {".tif", ".tiff", ".dcm"}
            or name.split(".")[0].rstrip().upper() in reserved or any(c in name for c in '<>:"/\\|?*')
            or any(ord(c) < 32 for c in name) or name.endswith((" ", "."))):
        raise ValueError("savePath 必须包含有效的 tif、tiff 或 dcm 文件名")
    root.mkdir(parents=True, exist_ok=True)
    target = root / name
    # Existing links must not redirect TIFF or either XML outside the fixed folder.
    for candidate in (target, target.with_suffix(".xml"), target.with_name(target.stem + "_ai.xml")):
        if candidate.is_symlink() or candidate.resolve().parent != root.resolve():
            raise ValueError("保存目标不能是符号链接或固定目录之外的路径")
    return target
