"""Public material identity summaries without retained spectral arrays."""


def public_fit_summary(metadata):
    return {key:metadata[key] for key in
            ('name','fingerprint','fit_metric','neutral_max_error_D')}
