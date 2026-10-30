// Copyright 2026 Yangming Feng
// SPDX-License-Identifier: GPL-3.0-or-later
// Preview-only CFA quartet gather. Black correction precedes this function;
// white balance and camera color conversion follow it in RawTherapee.
#pragma once
#include <array>
inline std::array<float,3> softloaf_bayer_quartet(const float values[4],const int colors[4]) {
    std::array<float,3> sum{{0,0,0}};
    int count[3]={0,0,0};
    for(int i=0;i<4;++i){const int channel=colors[i]==3?1:colors[i];sum[channel]+=values[i];++count[channel];}
    for(int c=0;c<3;++c)sum[c]/=count[c];
    return sum;
}
