#include "sentinel_core.hpp"
#include <cstring>
#include <cassert>

uint32_t sentinel_abi_version(void) {
    assert(SENTINEL_ABI_VERSION > 0);
    assert(SENTINEL_CACHE_CAPACITY > 0);
    return SENTINEL_ABI_VERSION;
}

size_t sentinel_arena_size(void) {
    assert(sizeof(SentinelMemoryArena) > 0);
    assert(sizeof(SentinelCacheEntry) > 0);
    return sizeof(SentinelMemoryArena);
}

size_t sentinel_cache_capacity(void) {
    assert(SENTINEL_CACHE_CAPACITY > 0);
    assert(SENTINEL_MAX_KEY_LEN > 1);
    return SENTINEL_CACHE_CAPACITY;
}

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

static bool is_valid_address(const char* addr) {
    assert(addr != nullptr);
    assert(SENTINEL_ADDRESS_LEN > 2);
    if (strnlen(addr, SENTINEL_ADDRESS_LEN + 1) != SENTINEL_ADDRESS_LEN) {
        return false;
    }
    if (addr[0] != '0' || (addr[1] != 'x' && addr[1] != 'X')) {
        return false;
    }
    for (size_t i = 2; i < SENTINEL_ADDRESS_LEN; ++i) {
        const char c = addr[i];
        const bool is_hex = (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
        if (!is_hex) {
            return false;
        }
    }
    return true;
}

static uint32_t decode_selector(const uint8_t* calldata, size_t len) {
    assert(calldata != nullptr);
    assert(len >= SENTINEL_SELECTOR_LEN);
    const uint32_t b0 = static_cast<uint32_t>(calldata[0]);
    const uint32_t b1 = static_cast<uint32_t>(calldata[1]);
    const uint32_t b2 = static_cast<uint32_t>(calldata[2]);
    const uint32_t b3 = static_cast<uint32_t>(calldata[3]);
    return (b0 << 24) | (b1 << 16) | (b2 << 8) | b3;
}

static int set_result(SentinelValidationResult* result, int code, const char* reason) {
    assert(result != nullptr);
    assert(reason != nullptr);
    result->status_code = code;
    std::strncpy(result->reason, reason, sizeof(result->reason) - 1);
    result->reason[sizeof(result->reason) - 1] = '\0';
    return code;
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

    if (!is_valid_address(to_address)) {
        return set_result(result, SENTINEL_ERR_INVALID_ADDRESS, "Target address is not a 0x-prefixed 20-byte hex address");
    }
    if (calldata == nullptr && calldata_len > 0) {
        return set_result(result, SENTINEL_ERR_NULL_PTR, "Calldata pointer is null but length is non-zero");
    }
    if (calldata_len > SENTINEL_MAX_CALLDATA_LEN) {
        return set_result(result, SENTINEL_ERR_CALLDATA_TOO_LARGE, "Calldata length exceeds 32KB bounded limit");
    }
    if (calldata_len > 0 && calldata_len < SENTINEL_SELECTOR_LEN) {
        return set_result(result, SENTINEL_ERR_MALFORMED_CALLDATA, "Calldata shorter than 4-byte function selector");
    }
    if (value_gwei > SENTINEL_MAX_VALUE_GWEI) {
        return set_result(result, SENTINEL_ERR_VALUE_EXCEEDED, "Transaction value exceeds 100 ETH ceiling");
    }
    if (gas_limit > SENTINEL_MAX_GAS_LIMIT) {
        return set_result(result, SENTINEL_ERR_GAS_EXCEEDED, "Gas limit exceeds 15M block ceiling");
    }
    if (calldata_len >= SENTINEL_SELECTOR_LEN) {
        result->selector = decode_selector(calldata, calldata_len);
    }
    return set_result(result, SENTINEL_OK, "Transaction passed all safety invariants");
}

static size_t find_slot(const SentinelMemoryArena* arena, const char* key) {
    assert(arena != nullptr);
    assert(key != nullptr);
    for (size_t i = 0; i < arena->count && i < SENTINEL_CACHE_CAPACITY; ++i) {
        const SentinelCacheEntry* entry = &arena->entries[i];
        if (entry->is_valid == 1 && std::strncmp(entry->key, key, SENTINEL_MAX_KEY_LEN) == 0) {
            return i;
        }
    }
    return SENTINEL_CACHE_CAPACITY;
}

int sentinel_cache_put(
    SentinelMemoryArena* arena,
    const char* key,
    const char* value,
    uint64_t expires_at_ns
) {
    assert(arena != nullptr);
    assert(key != nullptr && value != nullptr);

    if (arena == nullptr || key == nullptr || value == nullptr) {
        return SENTINEL_ERR_NULL_PTR;
    }
    if (arena->is_initialized != 1) {
        return SENTINEL_ERR_NOT_INITIALIZED;
    }
    const size_t key_len = strnlen(key, SENTINEL_MAX_KEY_LEN);
    if (key_len == 0) {
        return SENTINEL_ERR_INVALID_ARGUMENT;
    }
    if (key_len >= SENTINEL_MAX_KEY_LEN || strnlen(value, SENTINEL_MAX_VAL_LEN) >= SENTINEL_MAX_VAL_LEN) {
        return SENTINEL_ERR_BUFFER_TOO_SMALL;
    }

    // Overwrite an existing entry for this key in place so reads never see a stale value.
    size_t slot = find_slot(arena, key);
    const bool is_new = (slot == SENTINEL_CACHE_CAPACITY);
    if (is_new) {
        slot = arena->next_idx % SENTINEL_CACHE_CAPACITY;
    }
    SentinelCacheEntry* entry = &arena->entries[slot];
    std::memset(entry, 0, sizeof(SentinelCacheEntry));
    std::memcpy(entry->key, key, key_len);
    std::memcpy(entry->value, value, strnlen(value, SENTINEL_MAX_VAL_LEN));
    entry->expires_at_ns = expires_at_ns;
    entry->is_valid = 1;

    if (is_new) {
        arena->next_idx = (slot + 1) % SENTINEL_CACHE_CAPACITY;
        if (arena->count < SENTINEL_CACHE_CAPACITY) {
            arena->count++;
        }
    }
    return SENTINEL_OK;
}

int sentinel_cache_get(
    const SentinelMemoryArena* arena,
    const char* key,
    uint64_t now_ns,
    char* out_value,
    size_t out_max_len
) {
    assert(arena != nullptr);
    assert(key != nullptr && out_value != nullptr);

    if (arena == nullptr || key == nullptr || out_value == nullptr || out_max_len == 0) {
        return SENTINEL_ERR_NULL_PTR;
    }
    if (arena->is_initialized != 1) {
        return SENTINEL_ERR_NOT_INITIALIZED;
    }
    const size_t slot = find_slot(arena, key);
    if (slot == SENTINEL_CACHE_CAPACITY) {
        return SENTINEL_ERR_CACHE_NOT_FOUND;
    }
    const SentinelCacheEntry* entry = &arena->entries[slot];
    if (entry->expires_at_ns != 0 && now_ns >= entry->expires_at_ns) {
        return SENTINEL_ERR_CACHE_NOT_FOUND;
    }
    const size_t val_len = strnlen(entry->value, SENTINEL_MAX_VAL_LEN);
    if (val_len >= out_max_len) {
        return SENTINEL_ERR_BUFFER_TOO_SMALL;
    }
    std::memcpy(out_value, entry->value, val_len);
    out_value[val_len] = '\0';
    return SENTINEL_OK;
}
