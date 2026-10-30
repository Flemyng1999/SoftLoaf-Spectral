"""Sign, notarize and staple an explicitly staged macOS program-only payload.

Identity is a certificate identifier; the notarization credential stays in the
user's Keychain. This script never reads or exports a private key or password.
"""
import argparse
import json
from pathlib import Path
import subprocess

MAGIC={b'\xfe\xed\xfa\xce',b'\xce\xfa\xed\xfe',b'\xfe\xed\xfa\xcf',b'\xcf\xfa\xed\xfe',b'\xca\xfe\xba\xbe',b'\xbe\xba\xfe\xca'}


def run(*args):subprocess.run([str(x) for x in args],check=True)


def notarize(path,profile,receipt):
    result=subprocess.run(['xcrun','notarytool','submit',str(path),'--keychain-profile',profile,'--wait','--output-format','json'],capture_output=True,text=True,check=True)
    record=json.loads(result.stdout)
    receipt.parent.mkdir(parents=True,exist_ok=True);receipt.write_text(json.dumps(record,indent=2)+'\n')
    if record.get('status')!='Accepted':raise RuntimeError('Notarization was not accepted; receipt preserved')
    return record


def package(app,output,identity,profile,receipt):
    app=Path(app).resolve();output=Path(output).resolve();receipt=Path(receipt)
    if app.suffix!='.app' or not (app/'Contents/Resources/payload-inventory.json').is_file():raise ValueError('Use an inventoried staged application')
    if output.exists():raise FileExistsError(output)
    macho=[]
    for path in sorted(app.rglob('*')):
        if not path.is_file() or path.is_symlink():continue
        with path.open('rb') as stream:magic=stream.read(4)
        if magic in MAGIC:macho.append(path)
    if not macho:raise ValueError('No native executable payload')
    for path in macho:run('codesign','--force','--sign',identity,'--options','runtime','--timestamp',path)
    for framework in sorted(app.rglob('*.framework'),key=lambda p:len(p.parts),reverse=True):
        if framework.is_dir() and not framework.is_symlink():run('codesign','--force','--sign',identity,'--options','runtime','--timestamp',framework)
    run('codesign','--force','--sign',identity,'--options','runtime','--timestamp',app)
    run('codesign','--verify','--deep','--strict','--verbose=2',app)
    output.parent.mkdir(parents=True,exist_ok=True)
    submission=output.with_suffix('.app-notarization.zip')
    if submission.exists():raise FileExistsError(submission)
    run('ditto','-c','-k','--keepParent',app,submission)
    notarize(submission,profile,receipt.with_name(receipt.stem+'-app.json'))
    run('xcrun','stapler','staple',app)
    run('xcrun','stapler','validate',app)
    run('spctl','--assess','--type','execute','--verbose=2',app)
    run('hdiutil','create','-volname','SoftLoaf Spectral','-srcfolder',app.parent,'-format','UDZO','-ov',output)
    run('codesign','--force','--sign',identity,'--timestamp',output)
    record=notarize(output,profile,receipt)
    run('xcrun','stapler','staple',output)
    run('xcrun','stapler','validate',output)
    run('spctl','--assess','--type','open','--context','context:primary-signature','--verbose=2',output)
    return record


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('app','output','receipt'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--identity',required=True);p.add_argument('--keychain-profile',required=True)
    a=p.parse_args();r=package(a.app,a.output,a.identity,a.keychain_profile,a.receipt);print(json.dumps({'notarization':r.get('status'),'submission_id':r.get('id')}))
