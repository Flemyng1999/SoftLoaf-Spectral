"""Frozen jobs, bounded queue and cancellation; exports default to one worker."""
from concurrent.futures import ThreadPoolExecutor
import copy
import threading
import time
import uuid
from experiments.gui_recipe_server import RecipeError
from .diagnostics import event
from .compute_policy import retry_cpu

class PhotoJobs:
    def __init__(self,render,*,workers=1,max_pending=4,name='photo-export'):
        self.max_pending=max_pending
        self.render=render;self.worker=ThreadPoolExecutor(max_workers=workers,thread_name_prefix=name)
        self.lock=threading.RLock();self.jobs={}
    def start(self,request):
        with self.lock:
            if sum(j['status'] in ('queued','running') for j in self.jobs.values())>=self.max_pending:raise RecipeError('queue_full','任务队列已满，请稍后再试。')
            while len(self.jobs)>=max(16,2*self.max_pending):
                old=next((k for k,j in self.jobs.items() if j['status'] not in ('queued','running')),None)
                if old is None:break
                del self.jobs[old]
            identifier=uuid.uuid4().hex;cancel=threading.Event()
            job={'id':identifier,'status':'queued','completed':0,'total':len(request['inputs']),'cancel':cancel}
            self.jobs[identifier]=job
            event('job.queued',job_id=identifier,action=request.get('action'),total=job['total'])
            self.worker.submit(self._run,job,copy.deepcopy(request))
            return self.get(identifier)
    def _run(self,job,request):
        started=time.monotonic()
        def progress(completed=None,*,phase=None,total=None):
            with self.lock:
                changed=(completed is not None and completed!=job['completed']) or (phase is not None and phase!=job.get('phase'))
                if completed is not None:job['completed']=completed
                if phase is not None:job['phase']=phase
                if total is not None:job['total']=total
                if changed:event('job.progress',job_id=job['id'],phase=job.get('phase'),completed=job['completed'],total=job['total'])
        with self.lock:job['status']='running'
        event('job.started',job_id=job['id'],action=request.get('action'))
        try:
            result=retry_cpu(self.render)(request,progress=progress,cancelled=job['cancel'].is_set)
            with self.lock:job.update(status='cancelled' if job['cancel'].is_set() else 'complete',result=result)
        except Exception as error:
            event('job.failed',job_id=job['id'],action=request.get('action'),code=getattr(error,'code',None),error=error)
            with self.lock:job.update(status='failed',error=str(error) if isinstance(error,RecipeError) else '导出失败，请检查原始文件。')
        finally:event('job.finished',job_id=job['id'],status=job['status'],elapsed_ms=round((time.monotonic()-started)*1000,3))
    def get(self,identifier,cancel=False):
        with self.lock:
            if identifier not in self.jobs:raise RecipeError('unknown_job','找不到导出任务。')
            job=self.jobs[identifier]
            if cancel:job['cancel'].set()
            return {'ok':True,**copy.deepcopy({k:v for k,v in job.items() if k!='cancel'})}
