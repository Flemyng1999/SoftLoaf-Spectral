from pathlib import Path
import subprocess
import numpy as np
import pytest


def test_short_edge_preview_keeps_small_images_and_never_upscales():
    from spectral_app.preview_policy import preview_size
    assert preview_size(6000,4000)==(3072,2048)
    assert preview_size(4000,6000)==(2048,3072)
    assert preview_size(3396//2,2262//2)==(1698,1131)
    assert preview_size(8000,1000)==(8000,1000)


def test_bayer_quartets_support_all_layouts_and_average_the_two_greens(tmp_path):
    root=Path(__file__).resolve().parents[1]
    source=tmp_path/'quartet.cc';source.write_text('''
#include "third_party/rawtherapee/rtengine/softloaf_bayer_superpixel.h"
#include <cassert>
int main(){
 const int layouts[4][4]={{0,1,1,2},{2,1,1,0},{1,0,2,1},{1,2,0,1}};
 for (const auto& layout:layouts){float values[4];int green=0;for(int i=0;i<4;i++)values[i]=layout[i]==0?10:layout[i]==2?30:(++green==1?18:22);
  const auto out=softloaf_bayer_quartet(values,layout);assert(out[0]==10);assert(out[1]==20);assert(out[2]==30);
 }
}
''')
    subprocess.run(['clang++','-std=c++11','-I',str(root),str(source),'-o',str(tmp_path/'quartet')],check=True,capture_output=True)
    subprocess.run([str(tmp_path/'quartet')],check=True)


def test_raw_preview_has_separate_settings_and_half_dimensions(tmp_path):
    from spectral_app.rawtherapee import RawTherapee
    root=Path(__file__).resolve().parents[1];source=root/'artifacts/hsi-raw-lut/raw/scene43_r5_ev+0_SYNTHETIC.dng'
    if not source.exists():pytest.skip('Local DNG unavailable')
    engine=RawTherapee(root,tmp_path)
    preview=engine.develop(source,preview=True)
    assert preview['ap1'].shape==(245,325,3)
    assert preview['metadata']['preview_method']=='bayer-2x2'
    assert preview['metadata']['original_size']==[650,490]
    full=engine.develop(source,routes=('ap1',))
    assert full['ap1'].shape==(490,650,3)
    assert preview['metadata']['settings_sha256']!=full['metadata']['settings_sha256']
    assert len(list(tmp_path.glob('*/manifest.json')))==2


def test_native_libraw_half_size_and_reentrant_openmp_archive(tmp_path):
    import json,os
    root=Path(__file__).resolve().parents[1]
    library=root/'build/rawtherapee/rtengine/libraw/lib/.libs/libraw_r.a'
    source=root/'artifacts/hsi-raw-lut/raw/scene43_r5_ev+0_SYNTHETIC.dng'
    if not library.exists() or not source.exists():pytest.skip('Build the integrated RT engine and supply the local DNG')
    binary=tmp_path/'native-half'
    subprocess.run(['clang++','-std=c++11','-DLIBRAW_FORCE_OPENMP','-Xclang','-fopenmp','-I/opt/homebrew/opt/libomp/include','-I'+str(root/'third_party/rawtherapee/rtengine/libraw'),str(root/'tests/libraw_half_size_reference.cpp'),str(library),'-L/opt/homebrew/opt/libomp/lib','-lomp','-L/opt/homebrew/opt/little-cms2/lib','-llcms2','-lz','-o',str(binary)],check=True,capture_output=True)
    result=subprocess.run([str(binary),str(source)],env={**os.environ,'OMP_NUM_THREADS':'4'},check=True,capture_output=True,text=True)
    report=json.loads(result.stdout)
    assert report['half_size']==1 and report['OpenMP_max_threads']==4
    assert report['max_quartet_error']==0 and report['dimensions']==[329,249]
    symbols=subprocess.run(['nm',str(library)],check=True,capture_output=True,text=True).stdout
    assert 'U ___kmpc_fork_call' in symbols
