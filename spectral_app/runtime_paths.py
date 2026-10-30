"""Read-only program resources, per-user state and user-supplied science inputs."""
import json
import os
from pathlib import Path
import sys


class SetupRequired(RuntimeError):
    pass


def packaged():
    return bool(getattr(sys,'frozen',False))


def resources():
    return Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1])).resolve()


def state_root():
    if not packaged():return resources()
    override=os.environ.get('SOFTLOAF_STATE_HOME')
    if override:result=Path(override)
    elif sys.platform=='darwin':result=Path.home()/'Library/Application Support/SoftLoafSpectral'
    elif sys.platform=='win32':result=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))/'SoftLoafSpectral'
    else:result=Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'softloaf-spectral'
    if not result.is_absolute() or result.resolve().is_relative_to(resources()):
        raise SetupRequired('Application state must be outside installed program resources.')
    return result


def state_path(relative):
    return state_root()/relative


def settings():
    path=state_root()/'runtime.json'
    try:record=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError) as error:raise SetupRequired('Select a scientific-data directory and external data volume before starting.') from error
    if record.get('schema')!=1:raise SetupRequired('Unsupported runtime settings; select data directories again.')
    for key in ('science_root','data_root','volume'):
        if not isinstance(record.get(key),str) or not Path(record[key]).is_absolute():
            raise SetupRequired('Runtime settings need absolute scientific-data and external-volume paths.')
    if not Path(record['data_root']).resolve().is_relative_to(Path(record['volume']).resolve()):
        raise SetupRequired('Pixel storage must be on the configured data volume.')
    return record


def science_root(root=None):
    explicit=Path(root) if root is not None else resources()
    if not packaged() or explicit.resolve()!=resources():return explicit
    result=Path(settings()['science_root'])
    if not result.is_dir():raise SetupRequired('The selected scientific-data directory is unavailable.')
    return result


def native_directory():
    return resources()/'native' if packaged() else resources()/'build'/('Release' if sys.platform=='win32' else '')
