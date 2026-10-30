import json
from concurrent.futures import ThreadPoolExecutor


def test_diagnostics_are_bounded_and_do_not_record_private_values(tmp_path):
    from spectral_app.diagnostics import DiagnosticLog
    log=DiagnosticLog(tmp_path,max_bytes=700,backups=2)
    for i in range(35):
        log.event('job.progress',job_id='id',completed=i,total=35,
                  phase='矫正预览 · private-photo.ARW',path='/private/photo',token='secret')
    log.close();files=list(tmp_path.glob('events.jsonl*'))
    assert 1<=len(files)<=3
    records=[json.loads(line) for path in files for line in path.read_text().splitlines()]
    assert records and all(r['event']=='job.progress' and r['schema']==1 for r in records)
    text=json.dumps(records)
    for private in ('private-photo','/private/photo','secret'):assert private not in text
    assert all(r['phase']=='矫正预览' for r in records)


def test_concurrent_records_and_exception_location_remain_valid_json(tmp_path):
    from spectral_app.diagnostics import DiagnosticLog
    log=DiagnosticLog(tmp_path)
    def work(i):log.event('job.finished',job_id=str(i),elapsed_ms=i,status='complete')
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(work,range(40)))
    try:raise ValueError('/private/secret.raw')
    except ValueError as error:log.event('job.failed',error=error)
    log.close();records=[json.loads(line) for line in (tmp_path/'events.jsonl').read_text().splitlines()]
    assert len(records)==41 and len({r['job_id'] for r in records[:-1]})==40
    assert records[-1]['error_type']=='ValueError' and records[-1]['stack']
    assert '/private' not in json.dumps(records)


def test_failed_job_records_terminal_state_and_elapsed_time_without_user_text(tmp_path,monkeypatch):
    from spectral_app import diagnostics
    from spectral_app.photo_jobs import PhotoJobs
    from experiments.gui_recipe_server import RecipeError
    log=diagnostics.DiagnosticLog(tmp_path);monkeypatch.setattr(diagnostics,'_runtime',log)
    def fail(request,**kwargs):raise RecipeError('test_failure','private user filename.ARW')
    jobs=PhotoJobs(fail);job=jobs.start({'inputs':['retained-stage'],'action':'export'});jobs.worker.shutdown()
    assert jobs.get(job['id'])['status']=='failed'
    log.close();records=[json.loads(line) for line in (tmp_path/'events.jsonl').read_text().splitlines()]
    assert [r['event'] for r in records]==['job.queued','job.started','job.failed','job.finished']
    assert records[2]['code']=='test_failure' and records[3]['elapsed_ms']>=0
    assert 'private user' not in json.dumps(records)


def test_http_failure_is_logged_without_exposing_private_details(tmp_path,monkeypatch):
    import threading,urllib.request,urllib.error
    from types import SimpleNamespace
    from spectral_app import diagnostics
    from experiments.gui_recipe_server import make_server
    log=diagnostics.DiagnosticLog(tmp_path/'logs');monkeypatch.setattr(diagnostics,'_runtime',log)
    def fail(request):raise RuntimeError('/private/photo.ARW')
    server=make_server(SimpleNamespace(evaluate=fail),tmp_path/'index.html',tmp_path/'logo.png',0)
    worker=threading.Thread(target=server.serve_forever);worker.start()
    try:
        request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/evaluate',data=b'{}',headers={'Content-Type':'application/json'})
        try:urllib.request.urlopen(request)
        except urllib.error.HTTPError as error:
            assert error.code==500 and '/private/' not in error.read().decode()
        else:raise AssertionError('Expected failed request')
    finally:server.shutdown();worker.join();server.server_close();log.close()
    records=[json.loads(line) for line in (tmp_path/'logs/events.jsonl').read_text().splitlines()]
    assert records[0]['event']=='request.failed' and records[0]['code']=='computation_failed'
    assert records[0]['error_type']=='RuntimeError' and '/private/' not in json.dumps(records)
