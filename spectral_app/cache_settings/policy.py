"""Machine preferences; capacity-derived disk limits, separate free-space reserve."""
import os
import sys


def physical_memory_bytes():
    """OS physical capacity; conservative fallback if the query is unavailable."""
    try:
        if sys.platform=='win32':
            import ctypes as ct
            class MemoryStatus(ct.Structure):
                _fields_=[('dwLength',ct.c_uint32),('dwMemoryLoad',ct.c_uint32)]+[(name,ct.c_uint64) for name in ('ullTotalPhys','ullAvailPhys','ullTotalPageFile','ullAvailPageFile','ullTotalVirtual','ullAvailVirtual','ullAvailExtendedVirtual')]
            status=MemoryStatus();status.dwLength=ct.sizeof(status)
            query=ct.WinDLL('kernel32',use_last_error=True).GlobalMemoryStatusEx
            query.argtypes=[ct.POINTER(MemoryStatus)];query.restype=ct.c_int
            if query(ct.byref(status)) and status.ullTotalPhys:return status.ullTotalPhys
        else:
            value=os.sysconf('SC_PAGE_SIZE')*os.sysconf('SC_PHYS_PAGES')
            if value>0:return value
    except (AttributeError,OSError,ValueError):pass
    return 8*1024**3

GiB=1024**3
MiB=1024**2
DEFAULTS={'schema':1,'disk_mode':'automatic','disk_gib':4,'reserve_gib':None,'memory_mode':'automatic','memory_mib':1024,'location':None,'old_locations':[]}

def validate(values):
    allowed=set(DEFAULTS)-{'schema','old_locations'}
    if set(values)-allowed:raise ValueError('未知的缓存设置。')
    for key,choices in [('disk_mode',('automatic','custom','off')),('memory_mode',('automatic','custom'))]:
        if key in values and values[key] not in choices:raise ValueError('请选择有效的缓存模式。')
    for key,low,high in [('disk_gib',1,512),('reserve_gib',0,256),('memory_mib',256,8192)]:
        if key in values and not(key=='reserve_gib' and values[key] is None):
            value=values[key]
            if type(value) not in (float,int) or not low<=value<=high:raise ValueError('缓存容量超出允许范围。')
    if 'location' in values and values['location'] is not None and not isinstance(values['location'],str):raise ValueError('缓存位置无效。')
    return values

def budgets(settings,total,physical=None):
    physical=physical or physical_memory_bytes()
    memory=int(min(2048*MiB,max(512*MiB,physical//16))) if settings['memory_mode']=='automatic' else int(settings['memory_mib']*MiB)
    disk=int(min(8*GiB,max(2*GiB,total//100))) if settings['disk_mode']=='automatic' else int(settings['disk_gib']*GiB)
    reserve=int(min(16*GiB,max(2*GiB,total//50))) if settings['reserve_gib'] is None else int(settings['reserve_gib']*GiB)
    return {'disk_bytes':disk,'reserve_bytes':reserve,'memory_bytes':memory,'inputs_bytes':memory//2,
        'encoded_bytes':memory//8,'browser_bytes':memory//4,'working_bytes':min(128*MiB,max(16*MiB,memory//16))}
