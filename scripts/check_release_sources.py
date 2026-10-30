"""Verify the declared scientific payload and inherited source permissions.

This is a necessary data gate, not proof of installer, signing or runtime readiness.
No network access and no implicit approval or recursive collection of local assets.
"""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse


def check(review, root):
    root=Path(root).resolve();errors=[];assets={};visited=set();active=set()
    if review.get('schema')!=1:return ['Unsupported scientific source review schema']
    for item in review.get('assets',[]):
        key=item.get('id')
        if not key or key in assets:errors.append(f'{key}: duplicate or absent asset ID')
        else:assets[key]=item

    def local(key,field,value):
        if not isinstance(value,str) or not value:
            errors.append(f'{key}: missing {field}');return None
        p=(root/value).resolve()
        if Path(value).is_absolute() or not p.is_relative_to(root):
            errors.append(f'{key}: {field} outside candidate root');return None
        if not p.is_file():errors.append(f'{key}: missing {field} file');return None
        return p

    def visit(key):
        if key in active:errors.append(f'{key}: dependency cycle');return
        if key in visited:return
        item=assets.get(key)
        if item is None:errors.append(f'{key}: missing dependency record');return
        active.add(key)
        if item.get('status')!='approved':
            errors.append(f'{key}: {item.get("status","unreviewed")} distribution')
        else:
            source=urlparse(item.get('source',''))
            if source.scheme!='https' or not source.netloc:
                errors.append(f'{key}: missing original HTTPS source')
            kind=item.get('source_kind')
            if kind not in ('original','derived','upstream_repository'):
                errors.append(f'{key}: unreviewed source kind')
            repo_host=source.hostname in ('github.com','raw.githubusercontent.com','gitlab.com')
            if kind=='upstream_repository' or (repo_host and kind!='derived'):
                fallback=item.get('fallback',{})
                if (kind!='upstream_repository' or fallback.get('original_unavailable') is not True
                    or not fallback.get('reason') or not fallback.get('limitations')):
                    errors.append(f'{key}: undocumented or avoidable repository fallback')
                local(key,'fallback search_record',fallback.get('search_record'))
            p=local(key,'path',item.get('path'))
            if p and hashlib.sha256(p.read_bytes()).hexdigest()!=item.get('sha256'):
                errors.append(f'{key}: payload SHA-256 differs from reviewed bytes')
            local(key,'license_record',item.get('license_record'))
            if kind=='derived' and not item.get('dependencies'):
                errors.append(f'{key}: derived payload has no input records')
        for dep in item.get('dependencies',[]):visit(dep)
        active.remove(key);visited.add(key)

    roots=review.get('roots',[])
    if not roots:errors.append('No scientific payload roots declared')
    for key in roots:visit(key)
    for key in assets.keys()-visited:errors.append(f'{key}: unlisted asset outside dependency closure')
    return errors


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--review',type=Path,default=Path('release/scientific-sources.json'))
    args=parser.parse_args();review_path=args.review if args.review.is_absolute() else args.root/args.review
    errors=check(json.loads(review_path.read_text()),args.root)
    print(json.dumps({'scientific_payload_ready':not errors,'blockers':errors},indent=2))
    raise SystemExit(1 if errors else 0)
