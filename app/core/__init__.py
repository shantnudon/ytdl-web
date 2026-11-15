"""Download core packages.

Intentionally empty: importing submodules from here would pull in
``app.core.worker``, which imports ``app._ytdlp``, which imports
``app.core.jsruntime`` — a circular import. Import submodules directly instead.
"""
