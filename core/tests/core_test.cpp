#include "softloaf/core.h"
#include <cmath>
#include <cstring>
#include <iostream>

int main() {
    const double basis[] = {1,0, 0,1, 0,0};
    const double exposure[] = {1,0,1, 0,1,1};
    const double log_h[] = {-1,0};
    const double amounts[] = {1,1,1, 0,0,0};
    const double dyes[] = {1,0,0, 0,1,0};
    const double viewing[] = {.5,.5,0, .5,.5,1};
    const double light[] = {1,2};
    const double identity[] = {1,0,0, 0,1,0, 0,0,1};
    const double input[] = {.25,.5,.75};
    double output[18]{};
    SLReversal m{2,2,2,basis,exposure,log_h,amounts,dyes,viewing,light,identity,0,0,2};
    if (sl_abi_version() != 1 || sl_reversal(&m,input,1,output)) return 1;
    const double expected[] = {.25,.5, .25,.5,.75,
        .6020599913279624,.3010299956639812,.1249387366082999,
        .25,.5, .5,2, .75,.75,1, .75,.75,1};
    for (unsigned i=0; i<18; ++i) {
        if (std::abs(output[i]-expected[i]) > 1e-14) {
            std::cerr << "Incorrect intermediate at column " << i << '\n'; return 2;
        }
    }
    m.exposure_ev = 5;
    if (!sl_reversal(&m,input,1,output) || !std::strlen(sl_last_error())) return 3;
    m.exposure_ev = 0;
    if (sl_reversal(&m,input,1,output) || std::strlen(sl_last_error())) return 4;
    if (!sl_reversal(nullptr,input,1,output)) return 5;
    return 0;
}
