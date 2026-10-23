//go:build cgo && ((linux && (amd64 || arm64)) || (darwin && arm64))

package mosscore

/*
#cgo CFLAGS: -I${SRCDIR}/include
#include <stdlib.h>
#include <libmoss.h>
*/
import "C"

import (
	"fmt"
	"runtime"
	"sync"
	"unsafe"
)

type ManageClient struct {
	mu  sync.Mutex
	ptr *C.MossClient
}

type IndexManager struct {
	ptr    *C.MossClient
	mu     sync.RWMutex
	loaded map[string]struct{}
}

func NewManageClient(projectID, projectKey string) (*ManageClient, error) {
	ptr, err := newCClient(projectID, projectKey)
	if err != nil {
		return nil, err
	}
	client := &ManageClient{ptr: ptr}
	runtime.SetFinalizer(client, func(c *ManageClient) { _ = c.Close() })
	return client, nil
}

func (c *ManageClient) Close() error {
	if c == nil {
		return nil
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.ptr == nil {
		return nil
	}
	C.moss_client_free(c.ptr)
	c.ptr = nil
	return nil
}

func (c *ManageClient) CreateIndex(name string, docs []DocumentInfo, modelID string) (MutationResult, error) {
	input, err := newCDocumentInput(docs)
	if err != nil {
		return MutationResult{}, err
	}
	defer input.free()

	cName := C.CString(name)
	defer C.free(unsafe.Pointer(cName))

	var cModelID *C.char
	if modelID != "" {
		cModelID = C.CString(modelID)
		defer C.free(unsafe.Pointer(cModelID))
	}

	var out *C.MossMutationResult
	if err := c.withClient(func(ptr *C.MossClient) C.MossResult {
		return C.moss_client_create_index(ptr, cName, input.ptr(), C.uintptr_t(len(docs)), cModelID, &out)
	}); err != nil {
		return MutationResult{}, err
	}
	defer C.moss_free_mutation_result(out)

	return MutationResult{
		JobID:     goString(out.job_id),
		IndexName: goString(out.index_name),
		DocCount:  int(out.doc_count),
	}, nil
}

func (c *ManageClient) AddDocs(name string, docs []DocumentInfo, options *MutationOptions) (MutationResult, error) {
	input, err := newCDocumentInput(docs)
	if err != nil {
		return MutationResult{}, err
	}
	defer input.free()

	cName := C.CString(name)
	defer C.free(unsafe.Pointer(cName))

	var out *C.MossMutationResult
	var cOpts *C.MossMutationOptions
	if options != nil && options.Upsert != nil {
		cOpts = &C.MossMutationOptions{upsert: C.bool(*options.Upsert)}
	}

	if err := c.withClient(func(ptr *C.MossClient) C.MossResult {
		return C.moss_client_add_docs(ptr, cName, input.ptr(), C.uintptr_t(len(docs)), cOpts, &out)
	}); err != nil {
		return MutationResult{}, err
	}
	defer C.moss_free_mutation_result(out)

	return MutationResult{
		JobID:     goString(out.job_id),
		IndexName: goString(out.index_name),
		DocCount:  int(out.doc_count),
	}, nil
}

func (c *ManageClient) DeleteDocs(name string, docIDs []string) (MutationResult, error) {
	cName := C.CString(name)
	defer C.free(unsafe.Pointer(cName))

	ids := newCStringArray(docIDs)
	defer ids.free()

	var out *C.MossMutationResult
	if err := c.withClient(func(ptr *C.MossClient) C.MossResult {
		return C.moss_client_delete_docs(ptr, cName, ids.ptr(), C.uintptr_t(len(docIDs)), &out)
	}); err != nil {
		return MutationResult{}, err
	}
	defer C.moss_free_mutation_result(out)

	return MutationResult{
		JobID:     goString(out.job_id),
		IndexName: goString(out.index_name),
		DocCount:  int(out.doc_count),
	}, nil
}

func (c *ManageClient) GetJobStatus(jobID string) (JobStatusResponse, error) {
	cJobID := C.CString(jobID)
	defer C.free(unsafe.Pointer(cJobID))

	var out *C.MossJobStatusResponse
	if err := c.withClient(func(ptr *C.MossClient) C.MossResult {
		return C.moss_client_get_job_status(ptr, cJobID, &out)
	}); err != nil {
		return JobStatusResponse{}, err
	}
	defer C.moss_free_job_status_response(out)

	return JobStatusResponse{
		JobID:        goString(out.job_id),
		Status:       goString(out.status),
		Progress:     float64(out.progress),
		CurrentPhase: goOptionalString(out.current_phase),
		Error:        goOptionalString(out.error),
		CreatedAt:    goString(out.created_at),
		UpdatedAt:    goString(out.updated_at),
		CompletedAt:  goOptionalString(out.completed_at),
	}, nil
}

func (c *ManageClient) GetIndex(name string) (IndexInfo, error) {
	cName := C.CString(name)
	defer C.free(unsafe.Pointer(cName))

	var out *C.MossIndexInfo
	if err := c.withClient(func(ptr *C.MossClient) C.MossResult {
		return C.moss_client_get_index(ptr, cName, &out)
	}); err != nil {
		return IndexInfo{}, err
	}
	defer C.moss_free_index_info(out)

	return convertIndexInfo(out), nil
}

func (c *ManageClient) ListIndexes() ([]IndexInfo, error) {
	var out *C.MossIndexInfo
	var count C.uintptr_t
	if err := c.withClient(func(ptr *C.MossClient) C.MossResult {
		return C.moss_client_list_indexes(ptr, &out, &count)
	}); err != nil {
		return nil, err
	}
	defer C.moss_free_index_info_list(out, count)

	items := unsafe.Slice(out, int(count))
	response := make([]IndexInfo, 0, len(items))
	for i := range items {
		response = append(response, convertIndexInfo(&items[i]))
	}
	return response, nil
}

func (c *ManageClient) DeleteIndex(name string) (bool, error) {
	cName := C.CString(name)
	defer C.free(unsafe.Pointer(cName))

	var deleted C.bool
	if err := c.withClient(func(ptr *C.MossClient) C.MossResult {
		return C.moss_client_delete_index(ptr, cName, &deleted)
	}); err != nil {
		return false, err
	}
	return bool(deleted), nil
}

func (c *ManageClient) GetDocs(name string, docIDs []string) ([]DocumentInfo, error) {
	cName := C.CString(name)
	defer C.free(unsafe.Pointer(cName))

	ids := newCStringArray(docIDs)
	defer ids.free()

	var out *C.MossDocumentInfo
	var count C.uintptr_t
	if err := c.withClient(func(ptr *C.MossClient) C.MossResult {
		return C.moss_client_get_docs(ptr, cName, ids.ptr(), C.uintptr_t(len(docIDs)), &out, &count)
	}); err != nil {
		return nil, err
	}
	defer C.moss_free_documents(out, count)

	return convertDocuments(out, count), nil
}

func NewIndexManager(projectID, projectKey string) (*IndexManager, error) {
	ptr, err := newCClient(projectID, projectKey)
	if err != nil {
		return nil, err
	}
	manager := &IndexManager{
		ptr:    ptr,
		loaded: map[string]struct{}{},
	}
	runtime.SetFinalizer(manager, func(m *IndexManager) { _ = m.Close() })
	return manager, nil
}

func (m *IndexManager) Close() error {
	if m == nil {
		return nil
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.ptr == nil {
		return nil
	}
	C.moss_client_free(m.ptr)
	m.ptr = nil
	m.loaded = map[string]struct{}{}
	return nil
}

func (m *IndexManager) LoadIndex(indexName string, options *LoadIndexOptions) (IndexInfo, error) {
	cName := C.CString(indexName)
	defer C.free(unsafe.Pointer(cName))

	var out *C.MossIndexInfo
	var cOpts *C.MossLoadIndexOptions
	if options != nil {
		cOpts = &C.MossLoadIndexOptions{
			auto_refresh:          C.bool(options.AutoRefresh),
			polling_interval_secs: C.uint64_t(options.PollingIntervalInSeconds),
		}
	}

	if m == nil {
		return IndexInfo{}, ErrClientClosed
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.ptr == nil {
		return IndexInfo{}, ErrClientClosed
	}
	if err := withErrorThread(func() C.MossResult {
		return C.moss_client_load_index(m.ptr, cName, cOpts, &out)
	}); err != nil {
		return IndexInfo{}, err
	}
	defer C.moss_free_index_info(out)

	m.loaded[indexName] = struct{}{}
	return convertIndexInfo(out), nil
}

func (m *IndexManager) UnloadIndex(indexName string) error {
	cName := C.CString(indexName)
	defer C.free(unsafe.Pointer(cName))

	if m == nil {
		return ErrClientClosed
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.ptr == nil {
		return ErrClientClosed
	}
	if err := withErrorThread(func() C.MossResult {
		return C.moss_client_unload_index(m.ptr, cName)
	}); err != nil {
		return err
	}
	delete(m.loaded, indexName)
	return nil
}

func (m *IndexManager) HasIndex(indexName string) bool {
	m.mu.RLock()
	defer m.mu.RUnlock()
	_, ok := m.loaded[indexName]
	return ok
}

func (m *IndexManager) Query(indexName, query string, queryEmbedding []float32, topK int, alpha float32, filterJSON *string) (SearchResult, error) {
	return m.query(indexName, query, queryEmbedding, topK, alpha, filterJSON)
}

func (m *IndexManager) QueryText(indexName, query string, topK int, alpha float32, filterJSON *string) (SearchResult, error) {
	return m.query(indexName, query, nil, topK, alpha, filterJSON)
}

func (m *IndexManager) LoadQueryModel(indexName string) error {
	if m == nil {
		return ErrClientClosed
	}
	m.mu.RLock()
	defer m.mu.RUnlock()
	if m.ptr == nil {
		return ErrClientClosed
	}
	// libmoss loads bundled query models as part of moss_client_load_index.
	// Keep this method for parity with SDKs that expose explicit model loading.
	return nil
}

func (m *IndexManager) RefreshIndex(indexName string) (RefreshResult, error) {
	cName := C.CString(indexName)
	defer C.free(unsafe.Pointer(cName))

	var out *C.MossRefreshResult
	if err := m.withExclusiveClient(func(ptr *C.MossClient) C.MossResult {
		return C.moss_client_refresh_index(ptr, cName, &out)
	}); err != nil {
		return RefreshResult{}, err
	}
	defer C.moss_free_refresh_result(out)

	return RefreshResult{
		IndexName:         goString(out.index_name),
		PreviousUpdatedAt: goString(out.previous_updated_at),
		NewUpdatedAt:      goString(out.new_updated_at),
		WasUpdated:        bool(out.was_updated),
	}, nil
}

func (m *IndexManager) GetIndexInfo(indexName string) (IndexInfo, error) {
	cName := C.CString(indexName)
	defer C.free(unsafe.Pointer(cName))

	var out *C.MossIndexInfo
	if err := m.withClient(func(ptr *C.MossClient) C.MossResult {
		return C.moss_client_get_index(ptr, cName, &out)
	}); err != nil {
		return IndexInfo{}, err
	}
	defer C.moss_free_index_info(out)

	return convertIndexInfo(out), nil
}

func (m *IndexManager) query(indexName, query string, queryEmbedding []float32, topK int, alpha float32, filterJSON *string) (SearchResult, error) {
	cName := C.CString(indexName)
	defer C.free(unsafe.Pointer(cName))
	cQuery := C.CString(query)
	defer C.free(unsafe.Pointer(cQuery))

	var cFilter *C.char
	if filterJSON != nil {
		cFilter = C.CString(*filterJSON)
		defer C.free(unsafe.Pointer(cFilter))
	}

	var embeddingPtr *C.float
	var embeddingMem unsafe.Pointer
	if len(queryEmbedding) > 0 {
		embeddingMem = C.malloc(C.size_t(len(queryEmbedding)) * C.size_t(unsafe.Sizeof(C.float(0))))
		defer C.free(embeddingMem)
		embeddingSlice := unsafe.Slice((*C.float)(embeddingMem), len(queryEmbedding))
		for i, value := range queryEmbedding {
			embeddingSlice[i] = C.float(value)
		}
		embeddingPtr = (*C.float)(embeddingMem)
	}

	optsMem := C.malloc(C.size_t(unsafe.Sizeof(C.MossQueryOptions{})))
	defer C.free(optsMem)
	opts := (*C.MossQueryOptions)(optsMem)
	*opts = C.MossQueryOptions{
		top_k:         C.uintptr_t(topK),
		alpha:         C.float(alpha),
		filter_json:   cFilter,
		embedding:     embeddingPtr,
		embedding_dim: C.uintptr_t(len(queryEmbedding)),
	}

	var out *C.MossSearchResult
	if err := m.withClient(func(ptr *C.MossClient) C.MossResult {
		return C.moss_client_query(ptr, cName, cQuery, opts, &out)
	}); err != nil {
		return SearchResult{}, err
	}
	defer C.moss_free_search_result(out)

	docs := make([]QueryResultDocumentInfo, 0, int(out.doc_count))
	items := unsafe.Slice(out.docs, int(out.doc_count))
	for i := range items {
		item := items[i]
		docs = append(docs, QueryResultDocumentInfo{
			ID:       goString(item.id),
			Text:     goString(item.text),
			Metadata: convertMetadata(item.metadata, item.metadata_count),
			Score:    float64(item.score),
		})
	}

	return SearchResult{
		Docs:        docs,
		Query:       goString(out.query),
		IndexName:   goOptionalString(out.index_name),
		TimeTakenMs: int(out.time_taken_ms),
	}, nil
}

func newCClient(projectID, projectKey string) (*C.MossClient, error) {
	cProjectID := C.CString(projectID)
	defer C.free(unsafe.Pointer(cProjectID))
	cProjectKey := C.CString(projectKey)
	defer C.free(unsafe.Pointer(cProjectKey))

	var out *C.MossClient
	if err := withErrorThread(func() C.MossResult {
		return C.moss_client_new(cProjectID, cProjectKey, &out)
	}); err != nil {
		return nil, err
	}
	return out, nil
}

func (c *ManageClient) withClient(call func(*C.MossClient) C.MossResult) error {
	if c == nil {
		return ErrClientClosed
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.ptr == nil {
		return ErrClientClosed
	}
	return withErrorThread(func() C.MossResult {
		return call(c.ptr)
	})
}

func (m *IndexManager) withClient(call func(*C.MossClient) C.MossResult) error {
	if m == nil {
		return ErrClientClosed
	}
	m.mu.RLock()
	defer m.mu.RUnlock()
	if m.ptr == nil {
		return ErrClientClosed
	}
	return withErrorThread(func() C.MossResult {
		return call(m.ptr)
	})
}

func (m *IndexManager) withExclusiveClient(call func(*C.MossClient) C.MossResult) error {
	if m == nil {
		return ErrClientClosed
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.ptr == nil {
		return ErrClientClosed
	}
	return withErrorThread(func() C.MossResult {
		return call(m.ptr)
	})
}

func withErrorThread(call func() C.MossResult) error {
	runtime.LockOSThread()
	defer runtime.UnlockOSThread()
	return checkResult(call())
}

func checkResult(result C.MossResult) error {
	if result == C.OK {
		return nil
	}

	message := "libmoss call failed"
	if value := C.moss_last_error(); value != nil {
		message = C.GoString(value)
	}

	return fmt.Errorf("mosscore: %s (code %d)", message, int32(result))
}

func convertIndexInfo(info *C.MossIndexInfo) IndexInfo {
	return IndexInfo{
		ID:        goString(info.id),
		Name:      goString(info.name),
		Version:   goOptionalString(info.version),
		Status:    goString(info.status),
		DocCount:  int(info.doc_count),
		CreatedAt: goOptionalString(info.created_at),
		UpdatedAt: goOptionalString(info.updated_at),
		Model: ModelRef{
			ID:      goString(info.model.id),
			Version: goOptionalString(info.model.version),
		},
	}
}

func convertDocuments(out *C.MossDocumentInfo, count C.uintptr_t) []DocumentInfo {
	items := unsafe.Slice(out, int(count))
	response := make([]DocumentInfo, 0, len(items))
	for i := range items {
		item := items[i]
		var embedding []float32
		if item.embedding != nil && item.embedding_dim > 0 {
			embedding = make([]float32, int(item.embedding_dim))
			values := unsafe.Slice(item.embedding, int(item.embedding_dim))
			for j := range values {
				embedding[j] = float32(values[j])
			}
		}
		response = append(response, DocumentInfo{
			ID:        goString(item.id),
			Text:      goString(item.text),
			Metadata:  convertMetadata(item.metadata, item.metadata_count),
			Embedding: embedding,
		})
	}
	return response
}

func convertMetadata(entries *C.MossMetadataEntry, count C.uintptr_t) map[string]string {
	if entries == nil || count == 0 {
		return nil
	}
	items := unsafe.Slice(entries, int(count))
	response := make(map[string]string, len(items))
	for i := range items {
		response[goString(items[i].key)] = goString(items[i].value)
	}
	return response
}

func goString(value *C.char) string {
	if value == nil {
		return ""
	}
	return C.GoString(value)
}

func goOptionalString(value *C.char) *string {
	if value == nil {
		return nil
	}
	v := C.GoString(value)
	return &v
}

type cDocumentInput struct {
	docs        *C.MossDocumentInfo
	count       int
	allocations []unsafe.Pointer
	strings     []*C.char
}

func newCDocumentInput(docs []DocumentInfo) (*cDocumentInput, error) {
	input := &cDocumentInput{
		count: len(docs),
	}
	if len(docs) == 0 {
		return input, nil
	}

	docsMem := C.malloc(C.size_t(len(docs)) * C.size_t(unsafe.Sizeof(C.MossDocumentInfo{})))
	input.allocations = append(input.allocations, docsMem)
	input.docs = (*C.MossDocumentInfo)(docsMem)
	docSlice := unsafe.Slice(input.docs, len(docs))

	for i, doc := range docs {
		cID := C.CString(doc.ID)
		cText := C.CString(doc.Text)
		input.strings = append(input.strings, cID, cText)

		var metadataPtr *C.MossMetadataEntry
		if len(doc.Metadata) > 0 {
			metaMem := C.malloc(C.size_t(len(doc.Metadata)) * C.size_t(unsafe.Sizeof(C.MossMetadataEntry{})))
			input.allocations = append(input.allocations, metaMem)
			metaSlice := unsafe.Slice((*C.MossMetadataEntry)(metaMem), len(doc.Metadata))
			metaIndex := 0
			for key, value := range doc.Metadata {
				cKey := C.CString(key)
				cValue := C.CString(value)
				input.strings = append(input.strings, cKey, cValue)
				metaSlice[metaIndex] = C.MossMetadataEntry{
					key:   cKey,
					value: cValue,
				}
				metaIndex++
			}
			metadataPtr = (*C.MossMetadataEntry)(metaMem)
		}

		var embeddingPtr *C.float
		if len(doc.Embedding) > 0 {
			embeddingMem := C.malloc(C.size_t(len(doc.Embedding)) * C.size_t(unsafe.Sizeof(C.float(0))))
			input.allocations = append(input.allocations, embeddingMem)
			embeddingSlice := unsafe.Slice((*C.float)(embeddingMem), len(doc.Embedding))
			for j, value := range doc.Embedding {
				embeddingSlice[j] = C.float(value)
			}
			embeddingPtr = (*C.float)(embeddingMem)
		}

		docSlice[i] = C.MossDocumentInfo{
			id:             cID,
			text:           cText,
			metadata:       metadataPtr,
			metadata_count: C.uintptr_t(len(doc.Metadata)),
			embedding:      embeddingPtr,
			embedding_dim:  C.uintptr_t(len(doc.Embedding)),
		}
	}

	return input, nil
}

func (i *cDocumentInput) ptr() *C.MossDocumentInfo {
	return i.docs
}

func (i *cDocumentInput) free() {
	for _, ptr := range i.allocations {
		C.free(ptr)
	}
	for _, value := range i.strings {
		C.free(unsafe.Pointer(value))
	}
}

type cStringArray struct {
	valuesPtr **C.char
	count     int
	strings   []*C.char
	mem       unsafe.Pointer
}

func newCStringArray(values []string) *cStringArray {
	array := &cStringArray{count: len(values)}
	if len(values) == 0 {
		return array
	}
	array.mem = C.malloc(C.size_t(len(values)) * C.size_t(unsafe.Sizeof((*C.char)(nil))))
	array.valuesPtr = (**C.char)(array.mem)
	items := unsafe.Slice(array.valuesPtr, len(values))
	for i, value := range values {
		cValue := C.CString(value)
		array.strings = append(array.strings, cValue)
		items[i] = cValue
	}
	return array
}

func (a *cStringArray) ptr() **C.char {
	return a.valuesPtr
}

func (a *cStringArray) free() {
	if a.mem != nil {
		C.free(a.mem)
	}
	for _, value := range a.strings {
		C.free(unsafe.Pointer(value))
	}
}
