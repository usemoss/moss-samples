import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import MossDemo from './page'

vi.mock('next/image', () => ({
  default: ({ src, alt }: { src: string; alt: string }) => <img src={src} alt={alt} />,
}))

const mockClient = vi.hoisted(() => ({
  deleteIndex: vi.fn(),
  createIndex: vi.fn(),
  loadIndex: vi.fn(),
  query: vi.fn(),
}))

vi.mock('@moss-dev/moss-web', () => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  MossClient: vi.fn(function (this: any) { return mockClient }),
}))

const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { store = {} },
  }
})()
vi.stubGlobal('localStorage', localStorageMock)

beforeEach(() => {
  vi.clearAllMocks()
  localStorageMock.setItem('moss_credentials', JSON.stringify({ projectId: 'test-pid', projectKey: 'test-pkey' }))
  mockClient.deleteIndex.mockResolvedValue(undefined)
  mockClient.createIndex.mockResolvedValue(undefined)
  mockClient.loadIndex.mockResolvedValue(undefined)
  mockClient.query.mockResolvedValue({ docs: [], timeTakenMs: 3.4 })
})

// ── Helpers ────────────────────────────────────────────────────────────────

async function doBuildIndex(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: /build index/i }))
  await waitFor(() => expect(screen.getByText('Index ready to search')).toBeInTheDocument())
}

async function doLoadIndex(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: /load index/i }))
  await waitFor(() => expect(screen.getByText('✓ Ready')).toBeInTheDocument())
}

// The delete transition can still be pending (button reads "Deleting Index")
// for a render after its state updates land, so wait for the label to settle.
async function doDeleteIndex(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: /delete index/i }))
  await waitFor(() => {
    expect(screen.getByText('Build first')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /delete index/i })).toBeInTheDocument()
  })
}

// ── Tests ──────────────────────────────────────────────────────────────────

describe('MossDemo', () => {
  describe('initial render', () => {
    it('renders the 5 initial documents', () => {
      render(<MossDemo />)
      expect(screen.getAllByPlaceholderText('Type your content here…')).toHaveLength(5)
    })

    it('shows the document count badge as 5', () => {
      render(<MossDemo />)
      expect(screen.getByText('5')).toBeInTheDocument()
    })

    it('Build Index is enabled because all docs are modified', () => {
      render(<MossDemo />)
      expect(screen.getByRole('button', { name: /build index/i })).toBeEnabled()
    })

    it('Load Index is disabled before the index is built', () => {
      render(<MossDemo />)
      expect(screen.getByRole('button', { name: /load index/i })).toBeDisabled()
    })

    it('search input is disabled until the index is loaded', () => {
      render(<MossDemo />)
      expect(screen.getByPlaceholderText('Load index first…')).toBeDisabled()
    })

    it('shows "Build first" hint in search panel', () => {
      render(<MossDemo />)
      expect(screen.getByText('Build first')).toBeInTheDocument()
    })
  })

  describe('document management', () => {
    it('adds a new empty document row', async () => {
      const user = userEvent.setup()
      render(<MossDemo />)
      await user.click(screen.getByTitle('Add new document'))
      expect(screen.getAllByPlaceholderText('Type your content here…')).toHaveLength(6)
    })

    it('removes a document when its trash button is clicked', async () => {
      const user = userEvent.setup()
      render(<MossDemo />)
      await user.click(screen.getAllByTitle('Remove document')[0])
      expect(screen.getAllByPlaceholderText('Type your content here…')).toHaveLength(4)
    })

    it('shows empty state after all documents are removed', async () => {
      const user = userEvent.setup()
      render(<MossDemo />)
      for (const btn of screen.getAllByTitle('Remove document')) {
        await user.click(btn)
      }
      expect(screen.getByText('Start by adding your first document')).toBeInTheDocument()
    })
  })

  describe('buildIndex', () => {
    it('deletes the old index before creating a new one', async () => {
      const user = userEvent.setup()
      render(<MossDemo />)
      await doBuildIndex(user)
      expect(mockClient.deleteIndex).toHaveBeenCalledWith(expect.any(String))
      expect(mockClient.createIndex).toHaveBeenCalledTimes(1)
    })

    it('calls createIndex with all docs and the moss-minilm model', async () => {
      const user = userEvent.setup()
      render(<MossDemo />)
      await doBuildIndex(user)
      expect(mockClient.createIndex).toHaveBeenCalledWith(
        expect.any(String),
        expect.arrayContaining([expect.objectContaining({ id: 'doc-1' })]),
        { modelId: 'moss-minilm' }
      )
    })

    it('shows "Rebuild Index" label after a successful build', async () => {
      const user = userEvent.setup()
      render(<MossDemo />)
      await doBuildIndex(user)
      expect(screen.getByRole('button', { name: /rebuild index/i })).toBeInTheDocument()
    })

    it('shows an error message when createIndex rejects', async () => {
      mockClient.createIndex.mockRejectedValueOnce(new Error('API rate limit exceeded'))
      const user = userEvent.setup()
      render(<MossDemo />)
      await user.click(screen.getByRole('button', { name: /build index/i }))
      await waitFor(() =>
        expect(screen.getByText('API rate limit exceeded')).toBeInTheDocument()
      )
    })

    it('proceeds with createIndex even when deleteIndex throws', async () => {
      mockClient.deleteIndex.mockRejectedValueOnce(new Error('index not found'))
      const user = userEvent.setup()
      render(<MossDemo />)
      await doBuildIndex(user)
      expect(mockClient.createIndex).toHaveBeenCalledTimes(1)
    })
  })

  describe('loadIndexIntoMemory', () => {
    it('enables the search input after loading', async () => {
      const user = userEvent.setup()
      render(<MossDemo />)
      await doBuildIndex(user)
      await doLoadIndex(user)
      expect(screen.getByPlaceholderText('Type to search…')).toBeEnabled()
    })

    it('disables the Load Index button after successful load', async () => {
      const user = userEvent.setup()
      render(<MossDemo />)
      await doBuildIndex(user)
      await doLoadIndex(user)
      expect(screen.getByRole('button', { name: /index loaded/i })).toBeDisabled()
    })

    it('shows error in search panel when loadIndex rejects', async () => {
      mockClient.loadIndex.mockRejectedValueOnce(new Error('load failed'))
      const user = userEvent.setup()
      render(<MossDemo />)
      await doBuildIndex(user)
      await user.click(screen.getByRole('button', { name: /load index/i }))
      await waitFor(() => expect(screen.getByText('load failed')).toBeInTheDocument())
    })
  })

  describe('deleteIndex', () => {
    it('deletes the current index and returns the UI to the pre-build state', async () => {
      const user = userEvent.setup()
      render(<MossDemo />)
      await doBuildIndex(user)
      mockClient.deleteIndex.mockClear()
      await doDeleteIndex(user)

      expect(mockClient.deleteIndex).toHaveBeenCalledWith(expect.any(String))
      expect(screen.getByRole('button', { name: /build index/i })).toBeEnabled()
      expect(screen.getByRole('button', { name: /load index/i })).toBeDisabled()
    })

    it('shows an error message when deleting the index fails', async () => {
      const user = userEvent.setup()
      render(<MossDemo />)
      await doBuildIndex(user)
      mockClient.deleteIndex.mockRejectedValueOnce(new Error('delete failed'))

      await user.click(screen.getByRole('button', { name: /delete index/i }))

      await waitFor(() => {
        expect(screen.getByText('delete failed')).toBeInTheDocument()
        expect(screen.getByRole('button', { name: /delete index/i })).toBeEnabled()
      })
      expect(screen.queryByText('Index ready to search')).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: /load index/i })).toBeEnabled()
    })

    it('disables rebuild and load actions while deleting is in progress', async () => {
      let resolveDelete: (() => void) | undefined
      mockClient.deleteIndex.mockImplementationOnce(() => Promise.resolve(undefined))
      mockClient.createIndex.mockImplementationOnce(() => Promise.resolve(undefined))
      mockClient.deleteIndex.mockImplementationOnce(
        () =>
          new Promise<void>((resolve) => {
            resolveDelete = resolve
          })
      )

      const user = userEvent.setup()
      render(<MossDemo />)
      await doBuildIndex(user)

      await user.type(screen.getAllByPlaceholderText('Type your content here…')[0], ' updated')
      expect(screen.getByRole('button', { name: /rebuild index/i })).toBeEnabled()

      await user.click(screen.getByRole('button', { name: /delete index/i }))

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /rebuild index/i })).toBeDisabled()
      )
      expect(screen.getByRole('button', { name: /load index/i })).toBeDisabled()

      resolveDelete?.()
      await waitFor(() => expect(screen.getByText('Build first')).toBeInTheDocument())
    })

    it('disables delete while loading is in progress', async () => {
      let resolveLoad: (() => void) | undefined
      mockClient.loadIndex.mockImplementationOnce(
        () =>
          new Promise<string>((resolve) => {
            resolveLoad = () => resolve('demo-index')
          })
      )

      const user = userEvent.setup()
      render(<MossDemo />)
      await doBuildIndex(user)

      await user.click(screen.getByRole('button', { name: /load index/i }))

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /loading index/i })).toBeInTheDocument()
      )
      expect(screen.getByRole('button', { name: /delete index/i })).toBeDisabled()

      resolveLoad?.()
      await waitFor(() => expect(screen.getByText('✓ Ready')).toBeInTheDocument())
    })
  })

  describe('handleSearch', () => {
    it('calls query with the search term, topK: 5, and alpha: 0.5', async () => {
      const user = userEvent.setup()
      render(<MossDemo />)
      await doBuildIndex(user)
      await doLoadIndex(user)
      await user.type(screen.getByPlaceholderText('Type to search…'), 'latency')
      await waitFor(() =>
        expect(mockClient.query).toHaveBeenCalledWith(expect.any(String), 'latency', { topK: 5, alpha: 0.5 })
      )
    })

    it('renders result text and score for each returned doc', async () => {
      mockClient.query.mockResolvedValue({
        docs: [
          { id: 'doc-1', text: 'Moss is fast', score: 0.95, metadata: {} },
          { id: 'doc-2', text: 'Vector search', score: 0.72, metadata: {} },
        ],
        timeTakenMs: 4.2,
      })
      const user = userEvent.setup()
      render(<MossDemo />)
      await doBuildIndex(user)
      await doLoadIndex(user)
      await user.type(screen.getByPlaceholderText('Type to search…'), 'latency')
      await waitFor(() => expect(screen.getByText('Moss is fast')).toBeInTheDocument())
      expect(screen.getByText('Vector search')).toBeInTheDocument()
      expect(screen.getByText(/95%/)).toBeInTheDocument()
      expect(screen.getByText('Retrieval time 4.2 ms')).toBeInTheDocument()
    })

    it('shows empty state when query returns no docs', async () => {
      const user = userEvent.setup()
      render(<MossDemo />)
      await doBuildIndex(user)
      await doLoadIndex(user)
      await user.type(screen.getByPlaceholderText('Type to search…'), 'xyz')
      await waitFor(() =>
        expect(screen.getByText('No results found. Try a different query.')).toBeInTheDocument()
      )
    })

    it('shows error message when query rejects', async () => {
      mockClient.query.mockRejectedValue(new Error('search service unavailable'))
      const user = userEvent.setup()
      render(<MossDemo />)
      await doBuildIndex(user)
      await doLoadIndex(user)
      await user.type(screen.getByPlaceholderText('Type to search…'), 'x')
      await waitFor(() =>
        expect(screen.getByText('search service unavailable')).toBeInTheDocument()
      )
    })
  })
})
