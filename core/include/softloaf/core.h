#pragma once
#include <stdint.h>

#if defined(_WIN32)
#define SL_API __declspec(dllexport)
#else
#define SL_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* ABI 1: arrays are contiguous, row-major IEEE float64 unless explicitly declared. No ownership
 * transfer. Calls are synchronous and reentrant; errors belong to the thread.
 * Wavelength integration widths and light normalization are in supplied kernels.
 * C callers must provide the documented array lengths and output capacity. */
typedef struct {
    uint64_t source_count, view_count, curve_count;
    const double *basis;          /* [3, source_count], AP1/D60 -> reflectance */
    const double *exposure;       /* [source_count, 3], D65 energy SPD included */
    const double *log_h;          /* [curve_count], strictly increasing log10 H */
    const double *amounts;        /* [curve_count, 3], effective CMY amounts */
    const double *dyes;           /* [view_count, 3], optical density D */
    const double *view_kernel;    /* [view_count, 3], normalized observed XYZ */
    const double *viewed_light;   /* [view_count], SPD / perfect-transmitter Y */
    const double *adaptation;     /* [3, 3], observed XYZ -> interface XYZ D65 */
    double gray_log_h, exposure_ev, view_gain;
} SLReversal;

SL_API uint32_t sl_abi_version(void);
SL_API const char *sl_last_error(void);
SL_API int sl_acescct_decode(const double *input, uint64_t count, double *output);
/* output [count, source_count + 2*view_count + 12], columns in order:
 * estimated reflectance, layer H (3), CMY (3), transmission, viewed SPD,
 * observed XYZ (3), adapted XYZ D65 (3). */
SL_API int sl_reversal(const SLReversal *model, const double *ap1,
                      uint64_t count, double *output);
/* Generic exposure/development: spectra [count, source_count], kernel
 * [source_count,3], curves [curve_count,3], dyes [view_count,3], base
 * [view_count]. Output [count,6+view_count]: layer H, CMY, fraction T/R.
 * Source may be scene radiance or filtered enlarger radiance. */
SL_API int sl_spectral_stage(const double *spectra, uint64_t count,
    uint64_t source_count, const double *kernel, uint64_t curve_count,
    const double *log_h, const double *amounts, uint64_t view_count,
    const double *dyes, const double *base, double anchor, double ev,
    double *output);
/* table [edge, edge, edge, 3], RGB axes; clamp to domain, tetrahedral. */
SL_API int sl_cube_apply(const double *table, uint64_t edge,
                        const double *low, const double *high,
                        const double *input, uint64_t count, double *output);

/* Optional ABI-1 extension: CUBE-file red-fast float32 nodes, float64
 * coordinates, arithmetic and outputs. No full float64 table conversion. */
SL_API int sl_cube_apply_f32(const float *table, uint64_t edge,
                        const double *low, const double *high,
                        const double *input, uint64_t count, double *output);
#ifdef __cplusplus
}
#endif
