"""Personal external-data policy; project code and recipe workspace stay local."""
import hashlib
import json
import os
from pathlib import Path
import tempfile


class DataStorage:
    def __init__(self,root=None,volume=None,project=None):
        self.project=Path(project or Path(__file__).resolve().parents[1]).absolute()
        self.root=Path(root).absolute() if root else None
        self.volume=Path(volume).absolute() if volume else None
        if self.root and (not self.volume or not self.root.is_relative_to(self.volume)):
            raise ValueError('Data root must be on the configured external volume')

    @classmethod
    def configured(cls):
        project=Path(__file__).resolve().parents[1]
        settings=project/'local/storage-settings.json'
        if not settings.is_file():return cls(project=project)
        config=json.loads(settings.read_text())
        return cls(config['data_root'],config['volume'],project)

    def mounted(self):return bool(self.volume and self.volume.is_mount())

    def validate(self):
        if self.root:
            if not self.mounted():raise RuntimeError('请连接 T7 Touch。RAW 与高光谱数据不会改存到内置盘。')
            if not self.root.resolve().is_relative_to(self.volume.resolve()):raise RuntimeError('外置数据路径指向了其他磁盘。')

    def _external(self,path):
        path=Path(path).absolute()
        self.validate()
        if not self.root:return path
        if path.resolve().is_relative_to(self.volume.resolve()):return path.resolve()
        if path.is_relative_to(self.project):relative=path.relative_to(self.project)
        else:relative=Path('other-workspaces')/hashlib.sha256(str(path.parent).encode()).hexdigest()[:20]/path.name
        return self.root/'data'/relative

    def directory(self,path):
        path=Path(path).absolute();destination=self._external(path)
        if destination==path or not self.root:
            path.mkdir(parents=True,exist_ok=True);return path
        if path.is_symlink():
            if path.resolve()!=destination.resolve():raise RuntimeError('图像数据路径需要核对后迁移。')
            destination.mkdir(parents=True,exist_ok=True);return destination
        if path.exists():
            if not path.is_dir() or any(path.iterdir()):raise RuntimeError('已有图像数据需要先迁移至 T7；未自动覆盖。')
            path.rmdir()
        destination.mkdir(parents=True,exist_ok=True);path.parent.mkdir(parents=True,exist_ok=True)
        path.symlink_to(destination,target_is_directory=True)
        return destination

    def file(self,path):
        path=Path(path).absolute();destination=self._external(path);destination.parent.mkdir(parents=True,exist_ok=True)
        if self.root and destination!=path:
            if path.is_symlink():
                if path.resolve()!=destination.resolve():raise RuntimeError('RAW 原件路径需要核对后迁移。')
            elif path.exists():raise RuntimeError('已有 RAW 原件需要先迁移至 T7；未自动覆盖。')
            else:
                path.parent.mkdir(parents=True,exist_ok=True);path.symlink_to(destination)
        return destination

    def temporary_directory(self):
        self.validate()
        if not self.root:return Path(tempfile.gettempdir())
        path=self.root/'tmp';path.mkdir(parents=True,exist_ok=True);return path

    def activate_temporary_directory(self):
        if self.root:
            path=self.temporary_directory();os.environ['TMPDIR']=str(path);tempfile.tempdir=str(path)
