#!/usr/bin/env bash
# Usage: bundle-plotter.sh BUILD_DIR QT_PREFIX MAPLIBRE_PREFIX VERSION
# Creates cheekyplotter-VERSION-x86_64.tar.gz in the current directory and prints its name.
# BUILD_DIR is a Release build with CM_BUILD_PLOTTER=ON and CM_PLOTTER_TESTS=OFF. The bundle is
# relocatable: the binary has the classic RPATH $ORIGIN/../lib and bin/qt.conf points Qt at
# plugins/ and qml/.
# Layout: cheekyplotter-VERSION-x86_64/{bin/{cheekyplotter,qt.conf},lib/,plugins/,qml/,licenses/,
#         share/icons/hicolor/scalable/apps/cheekyplotter.svg,THIRD_PARTY_NOTICES,MANIFEST,DEPS,PACK_SCHEMA}
#   MANIFEST     one line per file: path, a tab, its SPDX license expression
#   DEPS         sonames the bundle needs from the system (NEEDED entries not in lib/)
#   PACK_SCHEMA  min=PLOTTER_PACK_SCHEMA_MIN and max=PLOTTER_PACK_SCHEMA_MAX from plotter/CMakeLists.txt
# lib/ holds only the ldd closure of the binary, plugins and QML plugins that lives under QT_PREFIX
# or MAPLIBRE_PREFIX, and must match LIB_ALLOW. Any path matching DENY (GPL-only Qt modules) fails.
set -euo pipefail

if [ $# -ne 4 ]; then
    echo "usage: $0 BUILD_DIR QT_PREFIX MAPLIBRE_PREFIX VERSION" >&2
    exit 2
fi

root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(cd "$1" && pwd)"
qt="$(cd "$2" && pwd)"
ml="$(cd "$3" && pwd)"
version="$4"
name="cheekyplotter-${version}-x86_64"

die() { echo "$0: $*" >&2; exit 1; }

# Qt and MapLibre libraries allowed in lib/ (all LGPL-3.0 Qt modules, Qt's ICU, libQMapLibre).
LIB_ALLOW='^(libQt6(Core|Gui|Network|Sql|Qml|QmlMeta|QmlModels|QmlWorkerScript|Quick|QuickControls2|QuickControls2Basic|QuickControls2BasicStyleImpl|QuickControls2Impl|QuickTemplates2|QuickLayouts|QuickShapes|Svg|OpenGL|DBus|WaylandClient|WaylandEglClientHwIntegration|WlShellIntegration|XcbQpa)\.so\.6|libicu[a-z0-9]*\.so\.[0-9]+|libQMapLibre[^/]*)$'
# Qt plugins copied (a trailing / copies every plugin in that directory).
PLUGINS=(
    platforms/libqxcb.so
    platforms/libqwayland-egl.so
    platforms/libqwayland-generic.so
    wayland-shell-integration/
    wayland-graphics-integration-client/
    wayland-decoration-client/
    xcbglintegrations/
    sqldrivers/libqsqlite.so
    imageformats/libqsvg.so
    imageformats/libqjpeg.so
    iconengines/libqsvgicon.so
    platforminputcontexts/libcomposeplatforminputcontextplugin.so
    platforminputcontexts/libibusplatforminputcontextplugin.so
)
# GPL-only Qt modules: none may enter the bundle.
DENY='VirtualKeyboard|virtualkeyboard|QtCharts|Charts|DataVisualization|Quick3DPhysics'
# The ICU license shipped in licenses/ is for this ICU major version.
ICU_MAJOR=73

cache="$build_dir/CMakeCache.txt"
grep -qx 'CMAKE_BUILD_TYPE:STRING=Release' "$cache" || die "$build_dir must be configured with -DCMAKE_BUILD_TYPE=Release"
grep -qx 'CM_PLOTTER_TESTS:BOOL=OFF' "$cache" || die "$build_dir must be configured with -DCM_PLOTTER_TESTS=OFF"
[ -e "$qt/lib/libicuuc.so.$ICU_MAJOR" ] || die "$qt/lib has no libicuuc.so.$ICU_MAJOR; update licenses/ for the new ICU"

schema_min="$(sed -n 's/^set(PLOTTER_PACK_SCHEMA_MIN \([0-9]*\))$/\1/p' "$root/plotter/CMakeLists.txt")"
schema_max="$(sed -n 's/^set(PLOTTER_PACK_SCHEMA_MAX \([0-9]*\))$/\1/p' "$root/plotter/CMakeLists.txt")"
[ -n "$schema_min" ] && [ -n "$schema_max" ] || die "no PLOTTER_PACK_SCHEMA_MIN/MAX in plotter/CMakeLists.txt"

rm -rf "$name"
mkdir -p "$name"
b="$PWD/$name"
# Only the plotter subdirectory: a build dir that also has n2kd must not put n2kd in the bundle.
cmake --install "$build_dir/plotter" --prefix "$b" >/dev/null
mkdir -p "$b/lib" "$b/plugins" "$b/qml" "$b/licenses"

for p in "${PLUGINS[@]}"; do
    case "$p" in
        */) [ -d "$qt/plugins/$p" ] || die "no plugin dir $qt/plugins/$p"
            mkdir -p "$b/plugins/$p"
            find "$qt/plugins/$p" -maxdepth 1 -name '*.so' -exec cp -L {} "$b/plugins/$p" \; ;;
        *)  [ -f "$qt/plugins/$p" ] || die "no plugin $qt/plugins/$p"
            mkdir -p "$b/plugins/$(dirname "$p")"
            cp -L "$qt/plugins/$p" "$b/plugins/$p" ;;
    esac
done

# QML modules: what qmlimportscanner finds for the plotter's QML, minus CheekyMarine (static, linked
# in). Each module's own files only; its subdirectories are other modules.
"$qt/libexec/qmlimportscanner" -rootPath "$root/plotter/qml" -rootPath "$root/plotter/src/qml" \
    -importPath "$qt/qml" > "$b/qml-imports.json"
modules="$(python3 -I -c '
import json, sys
qml = sys.argv[2] + "/"
for e in json.load(open(sys.argv[1])):
    if e.get("type") != "module" or e.get("name") == "CheekyMarine":
        continue
    path = e.get("path", "")
    if not path.startswith(qml):
        sys.exit("QML module %s is not under %s: %r" % (e.get("name"), qml, path))
    print(path[len(qml):])
' "$b/qml-imports.json" "$qt/qml")"
rm "$b/qml-imports.json"
for m in $modules; do
    mkdir -p "$b/qml/$m"
    find "$qt/qml/$m" -maxdepth 1 -type f -exec cp -L {} "$b/qml/$m" \;
done

# lib/: the ldd closure that lives under the two prefixes, copied under the soname.
for f in "$b/bin/cheekyplotter" $(find "$b/plugins" "$b/qml" -name '*.so' | LC_ALL=C sort); do
    LD_LIBRARY_PATH="$qt/lib:$ml/lib" ldd "$f" | awk '$2 == "=>" && $3 ~ /^\// {print $3}'
done | LC_ALL=C sort -u | while read -r lib; do
    case "$lib" in
        "$qt/lib/"*|"$ml/lib/"*) cp -L "$lib" "$b/lib/$(basename "$lib")" ;;
    esac
done

cat > "$b/bin/qt.conf" <<'EOF'
[Paths]
Prefix=..
Plugins=plugins
QmlImports=qml
EOF
printf 'min=%s\nmax=%s\n' "$schema_min" "$schema_max" > "$b/PACK_SCHEMA"
cp "$root/THIRD_PARTY_NOTICES" "$b/THIRD_PARTY_NOTICES"
cp "$root/LICENSE" "$b/licenses/CheekyMarine-LICENSE"
cp "$root/third_party/qt-6.8.3/LGPL-3.0-only.txt" "$root/third_party/qt-6.8.3/GPL-3.0-only.txt" \
    "$root/third_party/qt-6.8.3/icu-73.2-LICENSE" "$b/licenses/"
cp "$root/plotter/fonts/OFL.txt" "$b/licenses/NotoSans-OFL.txt"
cp "$root/plotter/icons/tabler/LICENSE" "$b/licenses/tabler-icons-LICENSE"

# Denylist first, so a GPL-only module is named as such, then the lib allowlist.
denied="$(cd "$b" && find . | sed 's|^\./||' | grep -E "$DENY" || true)"
if [ -n "$denied" ]; then
    echo "$0: GPL-only Qt file in the bundle: $denied" >&2
    exit 1
fi
for f in "$b"/lib/*; do
    basename "$f" | grep -Eq "$LIB_ALLOW" || die "lib/$(basename "$f") is not in the lib allowlist"
done

# DEPS: every NEEDED soname that lib/ does not provide.
(cd "$b" && find bin lib plugins qml -type f -name '*.so*' -o -type f -path 'bin/cheekyplotter') \
    | while read -r f; do readelf -d "$b/$f" | sed -n 's/.*(NEEDED).*\[\(.*\)\]$/\1/p'; done \
    | LC_ALL=C sort -u | while read -r so; do [ -e "$b/lib/$so" ] || echo "$so"; done > "$b/DEPS"

# MANIFEST: every file with its license; a file with no rule fails the build.
license_of() {
    case "$1" in
        bin/cheekyplotter) echo "MIT AND OFL-1.1" ;;
        lib/libQt6*|plugins/*|qml/*) echo "LGPL-3.0-only" ;;
        lib/libicu*) echo "Unicode-DFS-2016 AND ICU AND BSD-3-Clause AND NAIST-2003" ;;
        lib/libQMapLibre*) echo "BSD-2-Clause AND Unicode-DFS-2016 AND MIT AND curl AND Apache-2.0 AND BSD-3-Clause AND BSL-1.0 AND ISC" ;;
        licenses/*) echo "LicenseRef-license-text" ;;
        bin/qt.conf|THIRD_PARTY_NOTICES|MANIFEST|DEPS|PACK_SCHEMA|share/icons/hicolor/scalable/apps/cheekyplotter.svg) echo "MIT" ;;
        *) return 1 ;;
    esac
}
touch "$b/MANIFEST"
(cd "$b" && find . -type f | sed 's|^\./||' | LC_ALL=C sort) | while read -r f; do
    lic="$(license_of "$f")" || die "no license rule for $f"
    printf '%s\t%s\n' "$f" "$lic"
done > "$b.MANIFEST"
mv "$b.MANIFEST" "$b/MANIFEST"

tar --sort=name --owner=0 --group=0 --numeric-owner --mtime='2026-01-01 00:00:00Z' -cf - "$name" \
    | gzip -n > "${name}.tar.gz"
rm -rf "$name"
echo "${name}.tar.gz"
