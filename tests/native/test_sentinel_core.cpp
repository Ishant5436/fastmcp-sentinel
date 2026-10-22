// Native unit tests for the C++ invariant core.
// Built and run by CTest (see CMakeLists.txt); intended to run under ASan/UBSan in CI.

#include "sentinel_core.hpp"

#include <cstdio>
#include <cstring>
#include <string>

static int g_failures = 0;

static void check(bool cond, const char* what) {
    if (!cond) {
        std::fprintf(stderr, "FAIL: %s\n", what);
        ++g_failures;
    }
}

static SentinelMemoryArena g_arena;  // ~650KB: keep off the stack

static const char* kAddr = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640";

static void test_abi() {
    check(sentinel_abi_version() == SENTINEL_ABI_VERSION, "abi version");
    check(sentinel_arena_size() == sizeof(SentinelMemoryArena), "arena size");
    check(sentinel_cache_capacity() == SENTINEL_CACHE_CAPACITY, "capacity");
}

static void test_validate() {
    SentinelValidationResult r;
    const uint8_t transfer[] = {0xa9, 0x05, 0x9c, 0xbb, 0x00};
    check(sentinel_validate_tx(kAddr, transfer, sizeof(transfer), 1, 21000, &r) == SENTINEL_OK, "valid tx");
    check(r.selector == 0xa9059cbbU, "selector decoded");

    check(sentinel_validate_tx(kAddr, nullptr, 0, 0, 21000, &r) == SENTINEL_OK, "empty calldata ok");
    check(sentinel_validate_tx("0x1234", nullptr, 0, 0, 21000, &r) == SENTINEL_ERR_INVALID_ADDRESS, "short addr");
    check(sentinel_validate_tx("0xZZe6a0c2ddd26feeb64f039a2c41296fcb3f5640", nullptr, 0, 0, 21000, &r) ==
              SENTINEL_ERR_INVALID_ADDRESS,
          "non-hex addr");
    check(sentinel_validate_tx(kAddr, transfer, 3, 0, 21000, &r) == SENTINEL_ERR_MALFORMED_CALLDATA, "3-byte data");
    check(sentinel_validate_tx(kAddr, nullptr, 4, 0, 21000, &r) == SENTINEL_ERR_NULL_PTR, "null data w/ len");
    check(sentinel_validate_tx(kAddr, nullptr, 0, SENTINEL_MAX_VALUE_GWEI + 1, 21000, &r) ==
              SENTINEL_ERR_VALUE_EXCEEDED,
          "value ceiling");
    check(sentinel_validate_tx(kAddr, nullptr, 0, 0, SENTINEL_MAX_GAS_LIMIT + 1, &r) == SENTINEL_ERR_GAS_EXCEEDED,
          "gas ceiling");
    static uint8_t big[SENTINEL_MAX_CALLDATA_LEN + 1];
    check(sentinel_validate_tx(kAddr, big, sizeof(big), 0, 21000, &r) == SENTINEL_ERR_CALLDATA_TOO_LARGE,
          "calldata ceiling");
    check(std::strlen(r.reason) < sizeof(r.reason), "reason terminated");
}

static void test_cache() {
    char out[SENTINEL_MAX_VAL_LEN];
    check(sentinel_init_arena(&g_arena) == SENTINEL_OK, "init");

    check(sentinel_cache_put(&g_arena, "k", "old", 0) == SENTINEL_OK, "put old");
    check(sentinel_cache_put(&g_arena, "k", "new", 0) == SENTINEL_OK, "put new");
    check(sentinel_cache_get(&g_arena, "k", 1, out, sizeof(out)) == SENTINEL_OK && std::strcmp(out, "new") == 0,
          "overwrite returns latest value");
    check(g_arena.count == 1, "overwrite does not consume a slot");

    check(sentinel_cache_put(&g_arena, "ttl", "v", 100) == SENTINEL_OK, "put ttl");
    check(sentinel_cache_get(&g_arena, "ttl", 99, out, sizeof(out)) == SENTINEL_OK, "fresh hit");
    check(sentinel_cache_get(&g_arena, "ttl", 100, out, sizeof(out)) == SENTINEL_ERR_CACHE_NOT_FOUND, "expired");

    check(sentinel_cache_put(&g_arena, "", "v", 0) == SENTINEL_ERR_INVALID_ARGUMENT, "empty key");
    const std::string long_key(SENTINEL_MAX_KEY_LEN, 'a');
    check(sentinel_cache_put(&g_arena, long_key.c_str(), "v", 0) == SENTINEL_ERR_BUFFER_TOO_SMALL, "long key");
    const std::string long_val(SENTINEL_MAX_VAL_LEN, 'b');
    check(sentinel_cache_put(&g_arena, "lv", long_val.c_str(), 0) == SENTINEL_ERR_BUFFER_TOO_SMALL, "long val");

    char tiny[2];
    check(sentinel_cache_get(&g_arena, "k", 1, tiny, sizeof(tiny)) == SENTINEL_ERR_BUFFER_TOO_SMALL, "tiny buf");
    check(sentinel_cache_get(&g_arena, "missing", 1, out, sizeof(out)) == SENTINEL_ERR_CACHE_NOT_FOUND, "miss");

    // Fill past capacity: ring evicts oldest, never overflows.
    char key[32];
    for (size_t i = 0; i < SENTINEL_CACHE_CAPACITY + 10; ++i) {
        std::snprintf(key, sizeof(key), "key-%zu", i);
        check(sentinel_cache_put(&g_arena, key, "x", 0) == SENTINEL_OK, "fill put");
    }
    check(g_arena.count == SENTINEL_CACHE_CAPACITY, "count capped at capacity");
    check(sentinel_cache_get(&g_arena, "key-0", 1, out, sizeof(out)) == SENTINEL_ERR_CACHE_NOT_FOUND, "evicted");
    std::snprintf(key, sizeof(key), "key-%zu", SENTINEL_CACHE_CAPACITY + 9);
    check(sentinel_cache_get(&g_arena, key, 1, out, sizeof(out)) == SENTINEL_OK, "newest present");

    sentinel_reset_arena(&g_arena);
    check(g_arena.count == 0, "reset clears count");
}

int main() {
    test_abi();
    test_validate();
    test_cache();
    if (g_failures != 0) {
        std::fprintf(stderr, "%d native check(s) failed\n", g_failures);
        return 1;
    }
    std::printf("All native checks passed\n");
    return 0;
}
