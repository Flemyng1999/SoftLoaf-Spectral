import threading,time
from spectral_app.photo_jobs import PhotoJobs

def test_jobs_report_indeterminate_analysis_then_actual_image_progress():
    entered=threading.Event();release=threading.Event()
    def render(request,progress,cancelled):
        progress(0,phase='计算标定',total=0);entered.set();release.wait(2)
        progress(1.5,phase='刷新预览',total=3);return {}
    q=PhotoJobs(render)
    try:
        j=q.start({'inputs':['a']});assert entered.wait(2)
        a=q.get(j['id']);assert a['phase']=='计算标定' and a['total']==0
        release.set();q.worker.shutdown()
        a=q.get(j['id']);assert a['phase']=='刷新预览' and a['total']==3 and a['completed']==1.5
    finally:release.set()

def test_preparation_queue_is_bounded_and_can_overlap_two_jobs():
    from experiments.gui_recipe_server import RecipeError
    import pytest
    entered=threading.Barrier(3);release=threading.Event()
    def render(request,progress,cancelled):
        entered.wait(2);release.wait(3);return request
    queue=PhotoJobs(render,workers=2,max_pending=2,name='scan-prepare')
    try:
        a=queue.start({'inputs':['a']});b=queue.start({'inputs':['b']});entered.wait(2)
        with pytest.raises(RecipeError):queue.start({'inputs':['c']})
        assert queue.get(a['id'])['status']==queue.get(b['id'])['status']=='running'
    finally:release.set();queue.worker.shutdown()

def test_export_queue_freezes_inputs_and_reports_real_progress_and_cancel():
    entered=threading.Event();release=threading.Event();received=[]
    def render(request,progress,cancelled):
        entered.set();release.wait(3);received.append(request);progress(1)
        return {'cancelled':cancelled()}
    queue=PhotoJobs(render);request={'recipe':{'revision':2},'inputs':[{'id':'a','exposure_ev':.5}]}
    job=queue.start(request);assert entered.wait(2)
    request['recipe']['revision']=99;request['inputs'][0]['exposure_ev']=4
    queue.get(job['id'],cancel=True);release.set()
    for _ in range(100):
        actual=queue.get(job['id'])
        if actual['status']=='cancelled':break
        time.sleep(.01)
    assert actual['completed']==1 and actual['result']['cancelled']
    assert received==[{'recipe':{'revision':2},'inputs':[{'id':'a','exposure_ev':.5}]}]
    queue.worker.shutdown()
