"""Install pinned RT resources using upstream CMake's platform options mapping."""
import argparse
from pathlib import Path
import shutil


def install(source,destination,platform):
    source,destination=map(Path,(source,destination))
    option=source/'options'/('options.win' if platform=='windows' else 'options.osx' if platform=='macos' else 'options.lin')
    if not option.is_file():raise FileNotFoundError(option)
    camera_constants=source.parent/'rtengine/camconst.json'
    if not camera_constants.is_file():raise FileNotFoundError(camera_constants)
    destination.mkdir(parents=True,exist_ok=True)
    # Only the explicitly owned program-resource options directory is replaced.
    old=destination/'options'
    def removed_metadata(function,path,error):
        # exFAT can remove an AppleDouble companion as its primary file disappears.
        if not isinstance(error,FileNotFoundError):raise error
    if old.is_dir():shutil.rmtree(old,onexc=removed_metadata)
    for path in source.iterdir():
        if path.name=='options':continue
        target=destination/path.name
        if path.is_dir():shutil.copytree(path,target,dirs_exist_ok=True)
        elif path.is_file():shutil.copy2(path,target)
    shutil.copy2(option,old)
    # Upstream installs this rtengine file separately from rtdata.
    shutil.copy2(camera_constants,destination/'camconst.json')
    if not old.is_file() or old.read_bytes()!=option.read_bytes():raise RuntimeError('RT options installation differs')
    return destination

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--destination',type=Path,required=True)
    parser.add_argument('--platform',choices=('macos','windows','linux'),required=True)
    args=parser.parse_args();install(args.source,args.destination,args.platform)
