#include "MossRuntimeBridge.h"
#include <moss.h>
#include <string.h>

uint64_t moss_runtime_bridge_session_capabilities(void) {
#if defined(MOSS_IDENTITY_BOUND_API_VERSION) && MOSS_IDENTITY_BOUND_API_VERSION >= 2
    return moss_session_capabilities();
#else
    return 0;
#endif
}

const char *moss_runtime_bridge_last_error_detail(void) {
#if defined(MOSS_ERROR_DETAIL_API_VERSION) && MOSS_ERROR_DETAIL_API_VERSION >= 1
    return moss_last_error_detail();
#else
    return NULL;
#endif
}

int32_t moss_runtime_bridge_client_session_v2(
    void *client,
    const char *name,
    const char *model_id,
    uint8_t vector_quantization,
    uint8_t skip_auto_load_on_init,
    void *out_session
) {
    if (out_session == NULL) {
        return -5;
    }

    MossSession *session = NULL;
#if defined(MOSS_IDENTITY_BOUND_API_VERSION) && MOSS_IDENTITY_BOUND_API_VERSION >= 2
    MossSessionOptionsV2 options = {0};
    options.struct_size = (uint32_t)sizeof(options);
    options.version = MOSS_SESSION_OPTIONS_V2_VERSION;
    options.model_id = model_id;
    options.vector_quantization = vector_quantization;
    options.flags = skip_auto_load_on_init
        ? MOSS_SESSION_OPTIONS_V2_FLAG_SKIP_AUTO_LOAD_ON_INIT
        : 0;
    int32_t result = moss_client_session_v2(
        (MossClient *)client,
        name,
        &options,
        &session
    );
    memcpy(out_session, &session, sizeof(session));
    return result;
#else
    (void)client;
    (void)name;
    (void)model_id;
    (void)vector_quantization;
    (void)skip_auto_load_on_init;
    memcpy(out_session, &session, sizeof(session));
    return -5;
#endif
}

MossRuntimeBridgeFunction moss_runtime_bridge_session_embed_query_bound(void) {
#if defined(MOSS_IDENTITY_BOUND_API_VERSION) && MOSS_IDENTITY_BOUND_API_VERSION >= 2
    return (MossRuntimeBridgeFunction)moss_session_embed_query_bound;
#else
    return NULL;
#endif
}

MossRuntimeBridgeFunction moss_runtime_bridge_session_query_bound(void) {
#if defined(MOSS_IDENTITY_BOUND_API_VERSION) && MOSS_IDENTITY_BOUND_API_VERSION >= 2
    return (MossRuntimeBridgeFunction)moss_session_query_bound;
#else
    return NULL;
#endif
}

MossRuntimeBridgeFunction moss_runtime_bridge_bound_query_embedding_free(void) {
#if defined(MOSS_IDENTITY_BOUND_API_VERSION) && MOSS_IDENTITY_BOUND_API_VERSION >= 2
    return (MossRuntimeBridgeFunction)moss_bound_query_embedding_free;
#else
    return NULL;
#endif
}

MossRuntimeBridgeFunction moss_runtime_bridge_session_query(void) {
#if defined(MOSS_IDENTITY_BOUND_API_VERSION) && MOSS_IDENTITY_BOUND_API_VERSION >= 2
    return (MossRuntimeBridgeFunction)moss_session_query;
#else
    return NULL;
#endif
}

MossRuntimeBridgeFunction moss_runtime_bridge_session_query_with_model_identity(void) {
#if defined(MOSS_IDENTITY_BOUND_API_VERSION) && MOSS_IDENTITY_BOUND_API_VERSION >= 2
    return (MossRuntimeBridgeFunction)moss_session_query_with_model_identity;
#else
    return NULL;
#endif
}

MossRuntimeBridgeFunction moss_runtime_bridge_session_get_docs(void) {
#if defined(MOSS_IDENTITY_BOUND_API_VERSION) && MOSS_IDENTITY_BOUND_API_VERSION >= 2
    return (MossRuntimeBridgeFunction)moss_session_get_docs;
#else
    return NULL;
#endif
}

// ── Multi-index API ──────────────────────────────────────────────────

uint8_t moss_runtime_bridge_multi_index_available(void) {
#if defined(MOSS_MULTI_INDEX_API_VERSION) && MOSS_MULTI_INDEX_API_VERSION >= 1
    return 1;
#else
    return 0;
#endif
}

int32_t moss_runtime_bridge_client_load_indexes(
    void *client,
    const char *const *names,
    uintptr_t count,
    const void *opts,
    void **out_result
) {
    if (out_result == NULL) {
        return -5;
    }
    *out_result = NULL;
#if defined(MOSS_MULTI_INDEX_API_VERSION) && MOSS_MULTI_INDEX_API_VERSION >= 1
    MossLoadIndexesResult *result = NULL;
    int32_t r = moss_client_load_indexes(
        (MossClient *)client,
        names,
        count,
        (const MossLoadIndexOptions *)opts,
        &result
    );
    *out_result = result;
    return r;
#else
    (void)client;
    (void)names;
    (void)count;
    (void)opts;
    return -7;
#endif
}

int32_t moss_runtime_bridge_client_unload_indexes(
    void *client,
    const char *const *names,
    uintptr_t count
) {
#if defined(MOSS_MULTI_INDEX_API_VERSION) && MOSS_MULTI_INDEX_API_VERSION >= 1
    return moss_client_unload_indexes((MossClient *)client, names, count);
#else
    (void)client;
    (void)names;
    (void)count;
    return -7;
#endif
}

int32_t moss_runtime_bridge_client_query_multi_index(
    void *client,
    const char *const *names,
    uintptr_t count,
    const char *query,
    const void *opts,
    void **out_result
) {
    if (out_result == NULL) {
        return -5;
    }
    *out_result = NULL;
#if defined(MOSS_MULTI_INDEX_API_VERSION) && MOSS_MULTI_INDEX_API_VERSION >= 1
    MossSearchResult *result = NULL;
    int32_t r = moss_client_query_multi_index(
        (MossClient *)client,
        names,
        count,
        query,
        (const MossQueryOptions *)opts,
        &result
    );
    *out_result = result;
    return r;
#else
    (void)client;
    (void)names;
    (void)count;
    (void)query;
    (void)opts;
    return -7;
#endif
}

uintptr_t moss_runtime_bridge_load_indexes_loaded_count(const void *result) {
#if defined(MOSS_MULTI_INDEX_API_VERSION) && MOSS_MULTI_INDEX_API_VERSION >= 1
    const MossLoadIndexesResult *r = (const MossLoadIndexesResult *)result;
    return r == NULL ? 0 : r->loaded_count;
#else
    (void)result;
    return 0;
#endif
}

const char *moss_runtime_bridge_load_indexes_loaded_at(const void *result, uintptr_t i) {
#if defined(MOSS_MULTI_INDEX_API_VERSION) && MOSS_MULTI_INDEX_API_VERSION >= 1
    const MossLoadIndexesResult *r = (const MossLoadIndexesResult *)result;
    if (r == NULL || r->loaded == NULL || i >= r->loaded_count) {
        return NULL;
    }
    return r->loaded[i];
#else
    (void)result;
    (void)i;
    return NULL;
#endif
}

uintptr_t moss_runtime_bridge_load_indexes_failed_count(const void *result) {
#if defined(MOSS_MULTI_INDEX_API_VERSION) && MOSS_MULTI_INDEX_API_VERSION >= 1
    const MossLoadIndexesResult *r = (const MossLoadIndexesResult *)result;
    return r == NULL ? 0 : r->failed_count;
#else
    (void)result;
    return 0;
#endif
}

const char *moss_runtime_bridge_load_indexes_failed_name_at(const void *result, uintptr_t i) {
#if defined(MOSS_MULTI_INDEX_API_VERSION) && MOSS_MULTI_INDEX_API_VERSION >= 1
    const MossLoadIndexesResult *r = (const MossLoadIndexesResult *)result;
    if (r == NULL || r->failed == NULL || i >= r->failed_count) {
        return NULL;
    }
    return r->failed[i].name;
#else
    (void)result;
    (void)i;
    return NULL;
#endif
}

const char *moss_runtime_bridge_load_indexes_failed_error_at(const void *result, uintptr_t i) {
#if defined(MOSS_MULTI_INDEX_API_VERSION) && MOSS_MULTI_INDEX_API_VERSION >= 1
    const MossLoadIndexesResult *r = (const MossLoadIndexesResult *)result;
    if (r == NULL || r->failed == NULL || i >= r->failed_count) {
        return NULL;
    }
    return r->failed[i].error;
#else
    (void)result;
    (void)i;
    return NULL;
#endif
}

int32_t moss_runtime_bridge_load_indexes_failed_code_at(const void *result, uintptr_t i) {
#if defined(MOSS_MULTI_INDEX_API_VERSION) && MOSS_MULTI_INDEX_API_VERSION >= 1 \
    && defined(MOSS_ERROR_DETAIL_API_VERSION) && MOSS_ERROR_DETAIL_API_VERSION >= 1
    const MossLoadIndexesResult *r = (const MossLoadIndexesResult *)result;
    if (r == NULL || r->failed_codes == NULL || i >= r->failed_count) {
        return 0;
    }
    return (int32_t)r->failed_codes[i];
#else
    (void)result;
    (void)i;
    return 0;
#endif
}

void moss_runtime_bridge_free_load_indexes_result(void *result) {
#if defined(MOSS_MULTI_INDEX_API_VERSION) && MOSS_MULTI_INDEX_API_VERSION >= 1
    moss_free_load_indexes_result((MossLoadIndexesResult *)result);
#else
    (void)result;
#endif
}

const char *moss_runtime_bridge_query_result_doc_index_name(const void *doc) {
#if defined(MOSS_MULTI_INDEX_API_VERSION) && MOSS_MULTI_INDEX_API_VERSION >= 1
    const MossQueryResultDoc *d = (const MossQueryResultDoc *)doc;
    return d == NULL ? NULL : d->index_name;
#else
    (void)doc;
    return NULL;
#endif
}
