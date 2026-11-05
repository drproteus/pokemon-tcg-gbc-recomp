/*
 * spike_patch.c — minimal native-patch proof for the Pokémon TCG port.
 *
 * Hooks WaitForVBlank (bank 0, address 0x0264), which the game calls once per
 * frame. The pre/replace/post callbacks count invocations and print to stderr,
 * proving that the native-patch SDK dispatches into our C code on the
 * recompiled runtime without touching any guest memory.
 *
 * This is a mechanism spike, not a gameplay change. The obvious next step is
 * to bind a real QoL target (e.g. text speed) and mutate reviewed guest state
 * through the bounded gameplay-mutation API instead of just logging.
 */
#include "gbrt_native_patch.h"

#include <stdio.h>

static unsigned long g_pre = 0;
static unsigned long g_post = 0;

GB_NATIVE_HOOK(spike_pre) {
    (void)call;
    g_pre++;
    fprintf(stderr, "[spike] WaitForVBlank pre  #%lu\n", g_pre);
    return GB_NATIVE_STATUS_OK;
}

GB_NATIVE_REPLACEMENT(spike_replace) {
    /* Preserve the original body and its vblank timing; run post after RET. */
    return gb_native_call_original(call);
}

GB_NATIVE_HOOK(spike_post) {
    (void)call;
    g_post++;
    fprintf(stderr, "[spike] WaitForVBlank post #%lu\n", g_post);
    return GB_NATIVE_STATUS_OK;
}
