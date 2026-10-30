"""One reproducible check entry point; no dataset download or RAW-stage eviction."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]


def checked_report(path):
    cases=ET.parse(path).findall('.//testcase')
    if not cases:raise RuntimeError('Zero-test report is not verification')
    incomplete=[c.attrib.get('name') for c in cases if any(c.find(n) is not None for n in ('skipped','failure','error'))]
    if incomplete:raise RuntimeError('Required checks were skipped or failed: '+', '.join(incomplete))
    return {'tests':len(cases),'skipped':[]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',choices=['public','integration'],default='public')
    parser.add_argument('--build',type=Path,default=ROOT/'build')
    parser.add_argument('--report',type=Path,default=ROOT/'artifacts/quality/latest')
    args=parser.parse_args();args.report.mkdir(parents=True,exist_ok=True)
    suite=json.loads((ROOT/'quality/suites.json').read_text())
    report={'schema':1,'started':datetime.now(timezone.utc).isoformat(),'profile':args.profile,
        'platform':platform.platform(),'python_version':platform.python_version(),'steps':[],'ok':False}
    def run(name,command):
        started=time.monotonic()
        with (args.report/(name+'.log')).open('w',encoding='utf-8') as output:
            result=subprocess.run(command,cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,timeout=1200)
        report['steps'].append({'name':name,'returncode':result.returncode,'seconds':round(time.monotonic()-started,3)})
        print(name+': '+('passed' if result.returncode==0 else 'FAILED'),flush=True)
        if result.returncode:raise RuntimeError(name+' failed; inspect '+name+'.log')
    try:
        run('shader-sync',[sys.executable,'scripts/generate_hlsl.py','--check'])
        if args.profile=='integration':
            missing=[str(p) for p in suite['integration_required'] if not (ROOT/p).exists()]
            if missing:raise RuntimeError('Required integration inputs missing: '+', '.join(missing))
            run('preflight',[sys.executable,'-m','spectral_app','--check'])
        run('native',['ctest','--test-dir',str(args.build),'--output-on-failure','-C','Release','--output-junit',str((args.report/'native.xml').resolve())])
        report['native']=checked_report(args.report/'native.xml')
        js=sorted(str(p.relative_to(ROOT)) for p in (ROOT/'tests').glob('*.test.cjs') if not p.name.startswith('.'))
        if not js:raise RuntimeError('No JavaScript tests were discovered')
        run('javascript',['node','--test','--test-reporter=junit','--test-reporter-destination='+str((args.report/'javascript.xml').resolve()),*js])
        report['javascript']=checked_report(args.report/'javascript.xml')
        tests=suite['public'] if args.profile=='public' else ['tests']+(['--ignore=tests/test_d3d12_backend.py'] if sys.platform!='win32' else [])
        run('python',[sys.executable,'-m','pytest',*tests,'-q','--junitxml='+str((args.report/'python.xml').resolve()),
            '--cov=spectral_app','--cov=spectral_lut','--cov-report=xml:'+str((args.report/'coverage.xml').resolve()),
            '--cov-report=json:'+str((args.report/'coverage.json').resolve())])
        report['python']=checked_report(args.report/'python.xml')
        report['ok']=True
    except (OSError,RuntimeError,ET.ParseError,subprocess.TimeoutExpired) as error:
        report['error']=str(error);print(str(error),file=sys.stderr)
    finally:
        (args.report/'summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if report['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
