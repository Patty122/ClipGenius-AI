"""Maps transition style + measured visual discontinuity to FFmpeg xfade/acrossfade parameters."""
XFADE_FOR = {"smooth": ("fade", "fadeblack"), "fade": ("fade", "fadeblack"), "cut": ("cut", "cut"), "none": ("cut", "cut")}


def transition_type(style: str, discontinuity: float) -> str:
    low, high = XFADE_FOR.get(style, ("fade", "fadeblack"))
    return high if discontinuity >= 0.6 else low


SUPPORTED_XFADE = {"fade", "fadeblack", "dissolve", "wipeleft", "slideleft", "smoothleft"}
