# CAI Framework

# --- begin shim for optional dependencies ---
def is_pentestperf_available() -> bool:
    """
    Check if pentestperf is available as an optional dependency.
    """
    try:
        import importlib.util
        return importlib.util.find_spec("pentestperf") is not None
    except Exception:
        return False

def is_caiextensions_platform_available() -> bool:
    """
    Check if caiextensions platform is available as an optional dependency.
    """
    try:
        import importlib.util
        return importlib.util.find_spec("caiextensions") is not None
    except Exception:
        return False

def is_caiextensions_memory_available() -> bool:
    """
    Check if caiextensions memory is available as an optional dependency.
    """
    try:
        import importlib.util
        return importlib.util.find_spec("caiextensions") is not None
    except Exception:
        return False
# --- end shim ---