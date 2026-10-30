"""Versioned, source-limited image preview dimensions."""
PREVIEW_SHORT_EDGE=2048
PREVIEW_SCHEMA=3


def preview_size(width,height,limit=PREVIEW_SHORT_EDGE):
    if min(width,height,limit)<=0:raise ValueError('Invalid preview dimensions')
    scale=min(1.,limit/min(width,height))
    return max(1,round(width*scale)),max(1,round(height*scale))
