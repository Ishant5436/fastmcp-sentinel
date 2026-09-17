#ifndef SENTINEL_CORE_HPP
#define SENTINEL_CORE_HPP

#include <cstdint>
#include <cstddef>

#ifdef __cplusplus
extern "C" {
#endif

// Power of 10 Compile-Time Constants
constexpr size_t SENTINEL_MAX_CALLDATA_LEN = 32768;
constexpr size_t SENTINEL_CACHE_CAPACITY = 1024;
constexpr size_t SENTINEL_MAX_KEY_LEN = 128;
constexpr size_t SENTINEL_MAX_VAL_LEN = 512;
constexpr uint64_t SENTINEL_MAX_GAS_LIMIT = 15000000ULL;
// Value measured in Gwei (1 ETH = 10^9 Gwei) to prevent 64-bit integer overflow
constexpr uint64_t SENTINEL_MAX_VALUE_GWEI = 100ULL * 1000000000ULL; // 100 ETH ceiling

// Error & Status Codes
enum SentinelStatusCode : int {
    SENTINEL_OK = 0,
    SENTINEL_ERR_NULL_PTR = -1,
    SENTINEL_ERR_CALLDATA_TOO_LARGE = -2,
    SENTINEL_ERR_VALUE_EXCEEDED = -3,
    SENTINEL_ERR_GAS_EXCEEDED = -4,
    SENTINEL_ERR_REENTRANCY_SIGNATURE = -5,
    SENTINEL_ERR_CACHE_FULL = -6,
    SENTINEL_ERR_CACHE_NOT_FOUND = -7,
    SENTINEL_ERR_BUFFER_TOO_SMALL = -8
};

struct SentinelValidationResult {
    int status_code;
    uint32_t selector;
    uint64_t gas_limit;
    uint64_t value_gwei;
    char reason[128];
};

struct SentinelCacheEntry {
    char key[SENTINEL_MAX_KEY_LEN];
    char value[SENTINEL_MAX_VAL_LEN];
    uint64_t timestamp_ns;
    uint8_t is_valid;
};

struct SentinelMemoryArena {
    SentinelCacheEntry entries[SENTINEL_CACHE_CAPACITY];
    size_t count;
    size_t next_idx;
    uint8_t is_initialized;
};

// Interface exports (C ABI)
int sentinel_init_arena(SentinelMemoryArena* arena);
void sentinel_reset_arena(SentinelMemoryArena* arena);
int sentinel_validate_tx(
    const char* to_address,
    const uint8_t* calldata,
    size_t calldata_len,
    uint64_t value_gwei,
    uint64_t gas_limit,
    SentinelValidationResult* result
);
int sentinel_cache_put(
    SentinelMemoryArena* arena,
    const char* key,
    const char* value,
    uint64_t timestamp_ns
);
int sentinel_cache_get(
    const SentinelMemoryArena* arena,
    const char* key,
    char* out_value,
    size_t out_max_len
);

#ifdef __cplusplus
}
#endif

#endif // SENTINEL_CORE_HPP
