from types import SimpleNamespace
import ctypes


def test_windows_cache_budget_reads_physical_memory_without_sysconf(monkeypatch):
    import spectral_app.cache_settings.policy as policy
    monkeypatch.delattr(policy.os,'sysconf',raising=False)
    monkeypatch.setattr(policy.sys,'platform','win32')
    def status(pointer):
        assert pointer._obj.dwLength==64
        pointer._obj.ullTotalPhys=32*1024**3
        return 1
    monkeypatch.setattr(ctypes,'WinDLL',lambda *a,**kw:SimpleNamespace(GlobalMemoryStatusEx=status),raising=False)
    assert policy.budgets(policy.DEFAULTS,1024**4)['memory_bytes']==2*1024**3


def test_unavailable_memory_api_uses_bounded_conservative_budget(monkeypatch):
    import spectral_app.cache_settings.policy as policy
    monkeypatch.delattr(policy.os,'sysconf',raising=False)
    monkeypatch.setattr(policy.sys,'platform','other')
    assert policy.budgets(policy.DEFAULTS,1024**4)['memory_bytes']==512*1024**2
