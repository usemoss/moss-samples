//go:build !cgo || !((linux && (amd64 || arm64)) || (darwin && arm64))

package mosscore

type ManageClient struct{}

func NewManageClient(projectID, projectKey string) (*ManageClient, error) {
	return nil, ErrBindingsUnavailable
}

func (c *ManageClient) Close() error { return nil }

func (c *ManageClient) CreateIndex(name string, docs []DocumentInfo, modelID string) (MutationResult, error) {
	return MutationResult{}, ErrBindingsUnavailable
}

func (c *ManageClient) AddDocs(name string, docs []DocumentInfo, options *MutationOptions) (MutationResult, error) {
	return MutationResult{}, ErrBindingsUnavailable
}

func (c *ManageClient) DeleteDocs(name string, docIDs []string) (MutationResult, error) {
	return MutationResult{}, ErrBindingsUnavailable
}

func (c *ManageClient) GetJobStatus(jobID string) (JobStatusResponse, error) {
	return JobStatusResponse{}, ErrBindingsUnavailable
}

func (c *ManageClient) GetIndex(name string) (IndexInfo, error) {
	return IndexInfo{}, ErrBindingsUnavailable
}

func (c *ManageClient) ListIndexes() ([]IndexInfo, error) {
	return nil, ErrBindingsUnavailable
}

func (c *ManageClient) DeleteIndex(name string) (bool, error) {
	return false, ErrBindingsUnavailable
}

func (c *ManageClient) GetDocs(name string, docIDs []string) ([]DocumentInfo, error) {
	return nil, ErrBindingsUnavailable
}

type IndexManager struct{}

func NewIndexManager(projectID, projectKey string) (*IndexManager, error) {
	return nil, ErrBindingsUnavailable
}

func (m *IndexManager) Close() error { return nil }

func (m *IndexManager) LoadIndex(indexName string, options *LoadIndexOptions) (IndexInfo, error) {
	return IndexInfo{}, ErrBindingsUnavailable
}

func (m *IndexManager) UnloadIndex(indexName string) error {
	return ErrBindingsUnavailable
}

func (m *IndexManager) HasIndex(indexName string) bool {
	return false
}

func (m *IndexManager) Query(indexName, query string, queryEmbedding []float32, topK int, alpha float32, filterJSON *string) (SearchResult, error) {
	return SearchResult{}, ErrBindingsUnavailable
}

func (m *IndexManager) QueryText(indexName, query string, topK int, alpha float32, filterJSON *string) (SearchResult, error) {
	return SearchResult{}, ErrBindingsUnavailable
}

func (m *IndexManager) LoadQueryModel(indexName string) error {
	return ErrBindingsUnavailable
}

func (m *IndexManager) RefreshIndex(indexName string) (RefreshResult, error) {
	return RefreshResult{}, ErrBindingsUnavailable
}

func (m *IndexManager) GetIndexInfo(indexName string) (IndexInfo, error) {
	return IndexInfo{}, ErrBindingsUnavailable
}
