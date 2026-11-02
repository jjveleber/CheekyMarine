#!/usr/bin/env bash
# Usage: build-maplibre-qt.sh PREFIX
# Builds maplibre-native-qt (shared libraries, OpenGL renderer) at the pinned
# commit MLN_QT_COMMIT and installs it into PREFIX, for the Qt 6 found through
# CMAKE_PREFIX_PATH (for example CMAKE_PREFIX_PATH=$HOME/Qt/6.8.3/gcc_64).
# Afterwards PREFIX/lib/cmake/QMapLibre/QMapLibreConfig.cmake exists.
#
# The source checkout and build tree live in MLN_QT_WORK_DIR
# (default $HOME/.cache/cheekymarine/maplibre-native-qt); rerunning reuses them.
# See docs/plotter/spike-findings.md for why this commit and these options.
set -euo pipefail

MLN_QT_COMMIT=c3485f3a9590081c7be8edbc542341e688f6663d
MLN_QT_REPO=https://github.com/maplibre/maplibre-native-qt

if [ $# -ne 1 ]; then
    echo "usage: $0 PREFIX" >&2
    exit 2
fi
if [ -z "${CMAKE_PREFIX_PATH:-}" ]; then
    echo "$0: set CMAKE_PREFIX_PATH to the Qt 6 install (e.g. \$HOME/Qt/6.8.3/gcc_64)" >&2
    exit 1
fi

prefix="$(mkdir -p "$1" && cd "$1" && pwd)"
work="${MLN_QT_WORK_DIR:-$HOME/.cache/cheekymarine/maplibre-native-qt}"
src="$work/src"
build="$work/build"

if [ ! -d "$src/.git" ]; then
    mkdir -p "$work"
    git clone --quiet "$MLN_QT_REPO" "$src"
fi
# Fetch only when the pinned commit is not already present, so a rerun works offline.
if ! git -C "$src" cat-file -e "$MLN_QT_COMMIT^{commit}" 2>/dev/null; then
    git -C "$src" fetch --quiet origin
fi
git -C "$src" checkout --quiet --detach "$MLN_QT_COMMIT"

# Initialise only the submodules the core library build needs, each shallow. The full
# recursive checkout is about 8.5 GB (Windows vcpkg, boost history, Vulkan, docs themes).
git -C "$src" submodule update --init --depth 1 vendor/maplibre-native
git -C "$src/vendor/maplibre-native" submodule update --init --depth 1 -- \
    vendor/PMTiles \
    vendor/benchmark \
    vendor/boost \
    vendor/earcut.hpp \
    vendor/eternal \
    vendor/expected-lite \
    vendor/filesystem \
    vendor/googletest \
    vendor/kdbush.hpp \
    vendor/maplibre-native-base/deps/cheap-ruler-cpp \
    vendor/maplibre-native-base/deps/geojson-vt-cpp \
    vendor/maplibre-native-base/deps/geojson.hpp \
    vendor/maplibre-native-base/deps/geometry.hpp \
    vendor/maplibre-native-base/deps/jni.hpp \
    vendor/maplibre-native-base/deps/pixelmatch-cpp \
    vendor/maplibre-native-base/deps/shelf-pack-cpp \
    vendor/maplibre-native-base/deps/variant \
    vendor/maplibre-tile-spec \
    vendor/polylabel \
    vendor/protozero \
    vendor/rapidjson \
    vendor/supercluster \
    vendor/unique_resource \
    vendor/unordered_dense \
    vendor/vector-tile \
    vendor/wagyu
git -C "$src/vendor/maplibre-native/vendor/maplibre-tile-spec" submodule update --init --depth 1 -- \
    cpp/vendor/earcut \
    cpp/vendor/fsst

# Options (see docs/plotter/spike-findings.md): OpenGL renderer (GLES on the
# Pi 5); bundled ICU so the build does not depend on the distro ICU version.
# Only the core library (BSD-2-Clause) is built: the plotter renders
# QMapLibre::Map in its own QQuickItem, so the Qt Location plugin (LGPL-3.0 or
# GPL, and it needs Qt Location private headers), the QML MapLibre item and
# the widgets library are switched off.
cmake -S "$src" -B "$build" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_SHARED_LIBS=ON \
    -DCMAKE_INSTALL_PREFIX="$prefix" \
    -DQT_VERSION_MAJOR=6 \
    -DMLN_WITH_OPENGL=ON \
    -DMLN_QT_WITH_INTERNAL_ICU=ON \
    -DMLN_QT_WITH_LOCATION=OFF \
    -DMLN_QT_WITH_QUICK_PLUGIN=OFF \
    -DMLN_QT_WITH_WIDGETS=OFF
cmake --build "$build"
cmake --install "$build"

test -f "$prefix/lib/cmake/QMapLibre/QMapLibreConfig.cmake"
echo "installed maplibre-native-qt $MLN_QT_COMMIT into $prefix"
