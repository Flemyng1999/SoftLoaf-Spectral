import pytest
from spectral_app.compute_policy import GPUUnavailable,choose_backend,retry_cpu


def test_missing_gpu_retains_cpu_and_strict_gpu_mode_reports_failure():
    def missing():raise RuntimeError('device unavailable')
    assert choose_backend('d3d12',missing) is None
    with pytest.raises(RuntimeError):choose_backend('d3d12',missing,strict=True)
    assert choose_backend('cpu',lambda:pytest.fail('CPU mode must not initialize a GPU')) is None


def test_runtime_retry_keeps_frozen_input_and_never_retries_validation_errors():
    calls=[];frozen={'calibration':'immutable','stage':'retained-half'}
    @retry_cpu
    def render(request):
        calls.append(request)
        if len(calls)==1:raise GPUUnavailable('context disabled')
        return 'CPU result'
    assert render(frozen)=='CPU result' and calls==[frozen,frozen]
    @retry_cpu
    def invalid():raise ValueError('bad material')
    with pytest.raises(ValueError):invalid()


def test_retry_is_bounded_if_cpu_path_also_fails():
    calls=[]
    @retry_cpu
    def broken():calls.append(1);raise GPUUnavailable('still unavailable')
    with pytest.raises(GPUUnavailable):broken()
    assert len(calls)==2


def test_scan_job_keeps_gpu_failure_distinct_from_material_validation():
    from spectral_app.scanning.service import ScanService
    service=ScanService.__new__(ScanService);calls=[]
    def preview(*args):
        calls.append(args)
        if len(calls)==1:raise GPUUnavailable('device removed')
    service._frame_preview=preview;service.state=lambda:{'ok':True}
    request={'action':'prepare','inputs':['retained-half-stage'],'profile':'frozen','geometry':{}}
    assert retry_cpu(service._execute)(request)=={'ok':True}
    assert len(calls)==2 and calls[0]==calls[1]
