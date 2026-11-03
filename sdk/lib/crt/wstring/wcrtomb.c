/*
 * msvcrt.dll mbcs functions
 *
 * Copyright 1999 Alexandre Julliard
 * Copyright 2000 Jon Griffths
 *
 * This library is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Lesser General Public
 * License as published by the Free Software Foundation; either
 * version 2.1 of the License, or (at your option) any later version.
 *
 * This library is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public
 * License along with this library; if not, write to the Free Software
 * Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301, USA
 */

#include <precomp.h>

/*********************************************************************
 *              wcrtomb (MSVCRT.@)
 */
size_t CDECL wcrtomb( char *dst, wchar_t ch, mbstate_t *s)
{
    if(s)
        *s = 0;
    return wctomb(dst, ch);
}

// Small hack: import stub to allow GCC's stdc++ to link (same as rand_s)
#if defined(__GNUC__) && (DLL_EXPORT_VERSION < 0x600)
#ifdef WIN64
const void* __imp_wcrtomb = wcrtomb;
#else
const void* _imp__wcrtomb = wcrtomb; // i386 symbols get an extra underscore
#endif
#endif
