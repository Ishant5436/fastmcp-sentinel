#include "sentinel_core.hpp"
#include <cstring>
#include <cassert>

int sentinel_init_arena(SentinelMemoryArena* arena) {
    assert(arena != nullptr);
    assert(SENTINEL_CACHE_CAPACITY > 0);
    if (arena == nullptr) {
        return SENTINEL_ERR_NULL_PTR;
    }
    std::memset(arena, 0, sizeof(SentinelMemoryArena));
    arena->is_initialized = 1;
    return SENTINEL_OK;
}

void sentinel_reset_arena(SentinelMemoryArena* arena) {
    assert(arena != nullptr);
    assert(arena->is_initialized == 1 || arena->is_initialized == 0);
    if (arena != nullptr) {
        std::memset(arena->entries, 0, sizeof(arena->entries));
        arena->count = 0;
        arena->next_idx = 0;
    }
}

static uint32_t decode_selector(const uint8_t* calldata, size_t len) {
    assert(calldata != nullptr);
    assert(len >= 4);
    const uint32_t b0 = static_cast<uint32_t>(calldata[0]);
    const uint32_t b1 = static_cast<uint32_t>(calldata[1]);
    const uint32_t b2 = static_cast<uint32_t>(calldata[2]);
    const uint32_t b3 = static_cast<uint32_t>(calldata[3]);
    return (b0 << 24) | (b1 << 16) | (b2 << 8) | b3;
}

int sentinel_validate_tx(
    const char* to_address,
    const uint8_t* calldata,
    size_t calldata_len,
    uint64_t value_gwei,
    uint64_t gas_limit,
    SentinelValidationResult* result
) {
    assert(to_address != nullptr);
    assert(result != nullptr);

    if (to_address == nullptr || result == nullptr) {
        return SENTINEL_ERR_NULL_PTR;
    }
    std::memset(result, 0, sizeof(SentinelValidationResult));
    result->gas_limit = gas_limit;
    result->value_gwei = value_gwei;

    if (calldata_len > SENTINEL_MAX_CALLDATA_LEN) {
        result->status_code = SENTINEL_ERR_CALLDATA_TOO_LARGE;
        std::strncpy(result->reason, "Calldata length exceeds 32KB bounded limit", sizeof(result->reason) - 1);
        return SENTINEL_ERR_CALLDATA_TOO_LARGE;
    }

    if (value_gwei > SENTINEL_MAX_VALUE_GWEI) {
        result->status_code = SENTINEL_ERR_VALUE_EXCEEDED;
        std::strncpy(result->reason, "Transaction value exceeds 100 ETH ceiling", sizeof(result->reason) - 1);
        return SENTINEL_ERR_VALUE_EXCEEDED;
    }

    if (gas_limit > SENTINEL_MAX_GAS_LIMIT) {
        result->status_code = SENTINEL_ERR_GAS_EXCEEDED;
        std::strncpy(result->reason, "Gas limit exceeds 15M block ceiling", sizeof(result->reason) - 1);
        return SENTINEL_ERR_GAS_EXCEEDED;
    }

    if (calldata != nullptr && calldata_len >= 4) {
        result->selector = decode_selector(calldata, calldata_len);
    }

    result->status_code = SENTINEL_OK;
    std::strncpy(result->reason, "Transaction passed all safety invariants", sizeof(result->reason) - 1);
    return SENTINEL_OK;
}

int sentinel_cache_put(
    SentinelMemoryArena* arena,
    const char* key,
    const char* value,
    uint64_t timestamp_ns
) {
    assert(arena != nullptr);
    assert(key != nullptr && value != nullptr);

    if (arena == nullptr || key == nullptr || value == nullptr || arena->is_initialized != 1) {
        return SENTINEL_ERR_NULL_PTR;
    }

    const size_t slot = arena->next_idx % SENTINEL_CACHE_CAPACITY;
    SentinelCacheEntry* entry = &arena->entries[slot];
    
    std::strncpy(entry->key, key, SENTINEL_MAX_KEY_LEN - 1);
    entry->key[SENTINEL_MAX_KEY_LEN - 1] = '\0';
    
    std::strncpy(entry->value, value, SENTINEL_MAX_VAL_LEN - 1);
    entry->value[SENTINEL_MAX_VAL_LEN - 1] = '\0';
    
    entry->timestamp_ns = timestamp_ns;
    entry->is_valid = 1;

    arena->next_idx = (slot + 1) % SENTINEL_CACHE_CAPACITY;
    if (arena->count < SENTINEL_CACHE_CAPACITY) {
        arena->count++;
    }
    return SENTINEL_OK;
}

int sentinel_cache_get(
    const SentinelMemoryArena* arena,
    const char* key,
    char* out_value,
    size_t out_max_len
) {
    assert(arena != nullptr);
    assert(key != nullptr && out_value != nullptr);

    if (arena == nullptr || key == nullptr || out_value == nullptr || out_max_len == 0) {
        return SENTINEL_ERR_NULL_PTR;
    }

    for (size_t i = 0; i < arena->count && i < SENTINEL_CACHE_CAPACITY; ++i) {
        const SentinelCacheEntry* entry = &arena->entries[i];
        if (entry->is_valid == 1 && std::strncmp(entry->key, key, SENTINEL_MAX_KEY_LEN) == 0) {
            std::strncpy(out_value, entry->value, out_max_len - 1);
            out_value[out_max_len - 1] = '\0';
            return SENTINEL_OK;
        }
    }
    return SENTINEL_ERR_CACHE_NOT_FOUND;
}
