#include "softloaf/core.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <stdexcept>
#include <string>
#include <span>

namespace {
thread_local std::string error;
void require(bool ok, const char* message) {
    if (!ok) throw std::invalid_argument(message);
}
template<class T> void finite(const T* values, uint64_t count, bool nonnegative = false) {
    require(values != nullptr, "Null array.");
    for (const auto value : std::span(values, count))
        require(std::isfinite(value) && (!nonnegative || value >= 0),
                "Nonfinite or invalid negative value.");
}
template<class F> int checked(F body) noexcept {
    try { error.clear(); body(); return 0; }
    catch (const std::exception& e) { error = e.what(); return 1; }
    catch (...) { error = "Unknown numerical failure."; return 1; }
}
double interp(const SLReversal& m, double x, unsigned channel) {
    if (x <= m.log_h[0]) return m.amounts[channel];
    if (x >= m.log_h[m.curve_count - 1]) return m.amounts[(m.curve_count - 1)*3 + channel];
    auto right = std::upper_bound(m.log_h, m.log_h + m.curve_count, x) - m.log_h;
    const auto left = right - 1;
    const double t = (x - m.log_h[left]) / (m.log_h[right] - m.log_h[left]);
    return m.amounts[left*3 + channel] + t*(m.amounts[right*3 + channel] - m.amounts[left*3 + channel]);
}
template<class T> int apply_cube_table(const T* table, uint64_t n, const double* low, const double* high, const double* input, uint64_t count, double* output, bool red_fast) {
    return checked([&] {
        require(n >= 2 && n <= 129 && output, "Invalid LUT dimensions or output.");
        finite(table, n*n*n*3); finite(low, 3); finite(high, 3); finite(input, count*3);
        for (unsigned c = 0; c < 3; ++c) require(high[c] > low[c], "Invalid LUT domain.");
        for (uint64_t p = 0; p < count; ++p) {
            std::array<uint64_t, 3> base;
            std::array<double, 3> f;
            for (unsigned c = 0; c < 3; ++c) {
                const double pos = std::clamp((input[p*3+c]-low[c])/(high[c]-low[c]), 0.0, 1.0)*(n-1);
                base[c] = std::min(static_cast<uint64_t>(pos), n-2);
                f[c] = pos - base[c];
            }
            std::array<unsigned, 3> order{0, 1, 2};
            std::stable_sort(order.begin(), order.end(), [&](unsigned a, unsigned b) { return f[a] > f[b]; });
            auto offset = [n,red_fast](const std::array<uint64_t, 3>& b) { return red_fast?((b[2]*n+b[1])*n+b[0])*3:((b[0]*n+b[1])*n+b[2])*3; };
            const auto c0 = offset(base);
            ++base[order[0]]; const auto c1 = offset(base);
            ++base[order[1]]; const auto c2 = offset(base);
            ++base[order[2]]; const auto c3 = offset(base);
            auto value=[table](uint64_t index){return static_cast<double>(table[index]);};
            for (unsigned c = 0; c < 3; ++c)
                output[p*3+c] = value(c0+c) + f[order[0]]*(value(c1+c)-value(c0+c)) +
                    f[order[1]]*(value(c2+c)-value(c1+c)) + f[order[2]]*(value(c3+c)-value(c2+c));
        }
    });
}
}

extern "C" {
uint32_t sl_abi_version() { return 1; }
const char* sl_last_error() { return error.c_str(); }

int sl_acescct_decode(const double* input, uint64_t count, double* output) {
    return checked([&] {
        finite(input, count); require(output, "Null output.");
        for (uint64_t i = 0; i < count; ++i) {
            output[i] = input[i] > 0.155251141552511 ?
                std::exp2(input[i]*17.52 - 9.72) :
                (input[i] - 0.0729055341958355)/10.5402377416545;
            require(std::isfinite(output[i]), "ACEScct overflow.");
        }
    });
}

int sl_reversal(const SLReversal* model, const double* ap1, uint64_t count, double* output) {
    return checked([&] {
        require(model && output, "Null model or output.");
        const auto& m = *model;
        require(m.source_count >= 2 && m.source_count <= 16384 &&
                m.view_count >= 2 && m.view_count <= 16384 &&
                m.curve_count >= 2 && m.curve_count <= 4096, "Invalid model dimensions.");
        finite(ap1, count*3); finite(m.basis, 3*m.source_count);
        finite(m.exposure, m.source_count*3, true); finite(m.log_h, m.curve_count);
        finite(m.amounts, m.curve_count*3, true); finite(m.dyes, m.view_count*3, true);
        finite(m.view_kernel, m.view_count*3); finite(m.viewed_light, m.view_count, true);
        finite(m.adaptation, 9);
        require(std::isfinite(m.gray_log_h) && std::isfinite(m.exposure_ev) &&
                m.exposure_ev >= -4 && m.exposure_ev <= 4 &&
                std::isfinite(m.view_gain) && m.view_gain > 0, "Invalid process settings.");
        for (uint64_t i = 1; i < m.curve_count; ++i)
            require(m.log_h[i] > m.log_h[i - 1], "Curve axis must strictly increase.");
        const uint64_t width = m.source_count + 2*m.view_count + 12;
        for (uint64_t p = 0; p < count; ++p) {
            double* r = output + p*width;
            double* h = r + m.source_count;
            double* a = h + 3;
            double* t = a + 3;
            double* v = t + m.view_count;
            double* xyz = v + m.view_count;
            double* adapted = xyz + 3;
            std::fill(h, h + 3, 0.0);
            std::fill(xyz, xyz + 3, 0.0);
            for (uint64_t s = 0; s < m.source_count; ++s) {
                r[s] = std::max(0.0, ap1[p*3]*m.basis[s] +
                    ap1[p*3+1]*m.basis[m.source_count+s] +
                    ap1[p*3+2]*m.basis[2*m.source_count+s]);
                for (unsigned c = 0; c < 3; ++c) h[c] += r[s]*m.exposure[s*3+c];
            }
            for (unsigned c = 0; c < 3; ++c) {
                h[c] *= std::exp2(m.exposure_ev);
                a[c] = interp(m, m.gray_log_h + std::log10(std::max(h[c], 1e-30)), c);
            }
            for (uint64_t s = 0; s < m.view_count; ++s) {
                double density = 0;
                for (unsigned c = 0; c < 3; ++c) density += a[c]*m.dyes[s*3+c];
                t[s] = std::pow(10.0, -density);
                v[s] = t[s]*m.viewed_light[s]*m.view_gain;
                for (unsigned c = 0; c < 3; ++c) xyz[c] += t[s]*m.view_kernel[s*3+c];
            }
            for (unsigned c = 0; c < 3; ++c) xyz[c] *= m.view_gain;
            for (unsigned c = 0; c < 3; ++c) {
                adapted[c] = 0;
                for (unsigned j = 0; j < 3; ++j) adapted[c] += xyz[j]*m.adaptation[c*3+j];
            }
            finite(r, width);
        }
    });
}

int sl_spectral_stage(const double* spectra, uint64_t count, uint64_t ns,
    const double* kernel, uint64_t nc, const double* log_h,
    const double* amounts, uint64_t nv, const double* dyes, const double* base,
    double anchor, double ev, double* output) {
    return checked([&] {
        require(ns >= 2 && nv >= 2 && nc >= 2 && output, "Invalid spectral stage dimensions.");
        finite(spectra, count*ns, true); finite(kernel, ns*3, true);
        finite(log_h, nc); finite(amounts, nc*3, true);
        // Net dye increments may be signed after Dmin subtraction. Passivity
        // belongs to the summed absolute density, not each basis vector.
        finite(dyes, nv*3); finite(base, nv, true);
        require(std::isfinite(anchor) && std::isfinite(ev) && std::abs(ev) <= 32,
                "Invalid exposure origin or EV.");
        for (uint64_t i=1; i<nc; ++i) require(log_h[i] > log_h[i-1], "Invalid exposure axis.");
        SLReversal m{}; m.curve_count=nc; m.log_h=log_h; m.amounts=amounts;
        for (uint64_t p=0; p<count; ++p) {
            auto h=output+p*(6+nv); auto a=h+3; auto t=a+3;
            std::fill(h,h+3,0.0);
            for (uint64_t s=0; s<ns; ++s)
                for (unsigned c=0; c<3; ++c) h[c]+=spectra[p*ns+s]*kernel[s*3+c];
            for (unsigned c=0; c<3; ++c) {
                h[c]*=std::exp2(ev);
                a[c]=interp(m,anchor+std::log10(std::max(h[c],1e-30)),c);
            }
            for (uint64_t s=0; s<nv; ++s) {
                double d=base[s];
                for (unsigned c=0; c<3; ++c) d+=a[c]*dyes[s*3+c];
                require(std::isfinite(d) && d>=0, "Invalid absolute spectral density.");
                t[s]=std::pow(10.0,-d);
            }
            finite(h,6+nv);
        }
    });
}

int sl_cube_apply(const double* table, uint64_t n, const double* low, const double* high,
                  const double* input, uint64_t count, double* output) {
    return apply_cube_table(table,n,low,high,input,count,output,false);
}
int sl_cube_apply_f32(const float* table, uint64_t n, const double* low, const double* high,
                      const double* input, uint64_t count, double* output) {
    return apply_cube_table(table,n,low,high,input,count,output,true);
}
}
