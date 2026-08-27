# SillyTavern extensions

This directory contains a snapshot of the extension functionality used with
MultiAgent BrainEngine.  The SillyTavern application itself is intentionally
not included in this repository.

## Install

1. Install a compatible version of [SillyTavern](https://github.com/SillyTavern/SillyTavern).
2. Copy the contents of `extensions/` into
   `SillyTavern/public/scripts/extensions/` in that installation.
3. Configure SillyTavern to use the BrainEngine OpenAI-compatible endpoint:
   `http://127.0.0.1:8001/v1`.

The files under `extensions/` originate from SillyTavern and retain their
upstream licensing.  Update this snapshot deliberately when updating the
SillyTavern installation.
