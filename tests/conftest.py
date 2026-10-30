import os
from pathlib import Path

cache = Path(__file__).resolve().parents[1]/'artifacts'
os.environ.setdefault('MPLCONFIGDIR', str(cache/'.matplotlib'))
os.environ.setdefault('XDG_CACHE_HOME', str(cache/'.cache'))


def pytest_configure(config):
    from spectral_app.storage import DataStorage
    import uuid
    storage=DataStorage.configured()
    if not storage.root:return
    storage.activate_temporary_directory()
    if config.option.basetemp is None:
        parent=storage.root/'tests';parent.mkdir(exist_ok=True)
        config.option.basetemp=str(parent/('pytest-'+uuid.uuid4().hex))
    elif not Path(config.option.basetemp).absolute().resolve().is_relative_to(storage.volume.resolve()):
        import pytest
        raise pytest.UsageError('当前工作区的 RAW/高光谱测试临时数据必须放在 T7 Touch。')


def pytest_sessionfinish(session,exitstatus):
    """Successful generated pixels are disposable, unlike application stages.
    Custom UUID basetemps disable pytest's usual numbered-directory retention.
    Remove only this successful run; keep failed runs available for diagnosis.
    """
    import re,shutil
    factory=getattr(session.config,'_tmp_path_factory',None)
    path=getattr(factory,'_basetemp',None)
    if exitstatus!=0 or path is None:return
    from spectral_app.storage import DataStorage
    storage=DataStorage.configured()
    path=Path(path)
    if (storage.root and not path.is_symlink() and re.fullmatch(r'pytest-[0-9a-f]{32}',path.name)
            and path.resolve().parent==(storage.root/'tests').resolve()):
        def vanished(function,item,error):
            if not isinstance(error,FileNotFoundError):raise error
        shutil.rmtree(path,onexc=vanished)
