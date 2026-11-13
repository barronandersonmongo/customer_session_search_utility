#pragma once

// Forced before libc headers on supported glibc builds. Fortification requires
// optimization; retain stronger settings supplied by the build environment.
#if defined(__OPTIMIZE__) && (!defined(_FORTIFY_SOURCE) || _FORTIFY_SOURCE < 2)
#undef _FORTIFY_SOURCE
#define _FORTIFY_SOURCE 2
#endif
