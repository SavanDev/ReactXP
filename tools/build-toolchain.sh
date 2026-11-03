#!/bin/bash
#
# Builds a modern i686-w64-mingw32 cross toolchain targeting msvcrt,
# configured like RosBE (static runtime, DWARF-2 exceptions, posix threads).
#
# Usage: tools/build-toolchain.sh <install-prefix> [work-dir]
#
# Needs a host C/C++ compiler, make, curl, flex, bison, m4 and texinfo.
# Takes ~20 min on 12 cores and ~7 GB in the work directory.
#
set -euo pipefail

PREFIX=$(realpath -m "${1:?usage: $0 <install-prefix> [work-dir]}")
WORK=$(realpath -m "${2:-$PREFIX-work}")
TARGET=i686-w64-mingw32
SRC=$WORK/src
BLD=$WORK/build
JOBS=$(nproc)

GCC_V=16.2.0
BINUTILS_V=2.46.1
MINGW_V=14.0.0

export PATH=$PREFIX/bin:$PATH
mkdir -p "$SRC" "$BLD" "$PREFIX"

step() { echo "=== $(date +%T) $*"; }

fetch() {
    local file=$SRC/$(basename "$1")
    if [ ! -f "$file" ]; then
        curl -fL --retry 3 -o "$file.part" "$1"
        mv "$file.part" "$file"
    fi
}

step "download"
fetch https://ftp.gnu.org/gnu/binutils/binutils-$BINUTILS_V.tar.xz
fetch https://ftp.gnu.org/gnu/gcc/gcc-$GCC_V/gcc-$GCC_V.tar.xz
fetch https://downloads.sourceforge.net/project/mingw-w64/mingw-w64/mingw-w64-release/mingw-w64-v$MINGW_V.tar.bz2

cd "$SRC"
[ -d binutils-$BINUTILS_V ] || tar xf binutils-$BINUTILS_V.tar.xz
[ -d gcc-$GCC_V ] || tar xf gcc-$GCC_V.tar.xz
[ -d mingw-w64-v$MINGW_V ] || tar xf mingw-w64-v$MINGW_V.tar.bz2
[ -d gcc-$GCC_V/gmp ] || (cd gcc-$GCC_V && ./contrib/download_prerequisites)

step "binutils"
mkdir -p "$BLD/binutils" && cd "$BLD/binutils"
"$SRC/binutils-$BINUTILS_V/configure" --target=$TARGET --prefix="$PREFIX" \
    --with-sysroot="$PREFIX" --disable-multilib --disable-nls --disable-werror
make -j"$JOBS" && make install

step "mingw-w64 headers"
mkdir -p "$BLD/headers" && cd "$BLD/headers"
"$SRC/mingw-w64-v$MINGW_V/mingw-w64-headers/configure" --host=$TARGET \
    --prefix="$PREFIX/$TARGET" --with-default-msvcrt=msvcrt
make install
ln -sfn "$TARGET" "$PREFIX/mingw"

GCC_CONF=(--target=$TARGET --prefix="$PREFIX" --with-sysroot="$PREFIX"
    --with-pkgversion="RosBE-modern"
    --disable-multilib --disable-nls --disable-werror --disable-shared --enable-static
    --enable-languages=c,c++ --disable-win32-registry
    --disable-sjlj-exceptions --with-dwarf2 --enable-threads=posix
    --enable-fully-dynamic-string --disable-libgomp --disable-libssp
    --disable-libquadmath --disable-lto)

step "gcc stage 1"
mkdir -p "$BLD/gcc" && cd "$BLD/gcc"
[ -f Makefile ] || "$SRC/gcc-$GCC_V/configure" "${GCC_CONF[@]}"
make -j"$JOBS" all-gcc && make install-gcc

step "mingw-w64 crt (msvcrt)"
mkdir -p "$BLD/crt" && cd "$BLD/crt"
"$SRC/mingw-w64-v$MINGW_V/mingw-w64-crt/configure" --host=$TARGET \
    --prefix="$PREFIX/$TARGET" --with-sysroot="$PREFIX" \
    --with-default-msvcrt=msvcrt --enable-lib32 --disable-lib64
make -j"$JOBS" && make install

step "winpthreads"
mkdir -p "$BLD/winpthreads" && cd "$BLD/winpthreads"
"$SRC/mingw-w64-v$MINGW_V/mingw-w64-libraries/winpthreads/configure" --host=$TARGET \
    --prefix="$PREFIX/$TARGET" --disable-shared --enable-static
make -j"$JOBS" && make install

step "gcc full"
cd "$BLD/gcc"
make -j"$JOBS" && make install

step "done"
"$PREFIX/bin/$TARGET-gcc" -v 2>&1 | tail -1
