#!/bin/bash
# build_with_wine.sh
# Requires: wine, wine-python, and a Windows Python installed under wine, or use docker with --platform=windows.
# This script is just a guide — cross-building reliably requires setting up wine and Windows Python.

echo "This script provides guidance only. Cross-building with wine is environment-specific."
echo "Recommended approach: run PyInstaller on a native Windows machine (or CI runner)."
