# Enhanced Finder MCP

A better version of macOS Finder that provides intelligent file search and indexing capabilities through the Model Context Protocol (MCP).

## Features

- **Hybrid Search**: Combines semantic search, keyword matching, and fuzzy filename search for comprehensive results
- **Multiple File Types**: Support for PDF, Excel, Word, PowerPoint, CSV, text files, and more
- **MCP Server**: Full Model Context Protocol server implementation  
- **Rich CLI**: Beautiful command-line interface using Rich library
- **Speed Optimized**: Larger chunk sizes and lower similarity thresholds for faster, more comprehensive search
- **Index Management**: Clear indexes and remove specific files as needed
- **Fast Retrieval**: Vector-based similarity search with FAISS for quick file discovery

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd better-finder-mcp
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Install the package:
```bash
pip install -e .
```

## Usage

### Command Line Interface

#### Initialize and Index Files
```bash
# Perform full indexing of configured paths
better-finder index --full

# Index a specific directory
better-finder index /path/to/directory

# Incremental indexing (only new/modified files)
better-finder index --incremental
```

#### Search Files
```bash
# Semantic search
better-finder search "financial reports quarterly"

# Search with file type filter
better-finder search "budget" --type excel

# Limit results
better-finder search "meeting notes" --max 5
```

#### Configuration
```bash
# List configured scan paths
better-finder config list

# Add a new scan path
better-finder config add ~/Documents/Projects

# Remove a scan path
better-finder config remove ~/Downloads
```

#### View Statistics
```bash
# Show indexing statistics
better-finder stats
```

#### View File Content
```bash
# Display file content
better-finder show /path/to/file.pdf

# Clear entire index
better-finder clear-index

# Remove specific file from index
better-finder remove-file /path/to/unwanted/file.pdf
```

### MCP Server

Start the MCP server for integration with MCP clients:

```bash
better-finder server
```

The server provides the following tools:
- `search_files`: Intelligent file search
- `index_files`: File indexing operations
- `get_file_content`: Retrieve file content
- `get_stats`: View indexing statistics
- `configure_paths`: Manage scan paths

## Configuration

The application uses sensible defaults but can be customized:

### Default Scan Paths
- `~/Documents`
- `~/Desktop`
- `~/Downloads`

### Supported File Types
- **Documents**: PDF, DOC, DOCX, TXT, MD, RTF, ODT
- **Spreadsheets**: XLSX, XLS, CSV, ODS
- **Presentations**: PPTX, PPT, ODP, Keynote
- **Data**: JSON, XML

### File Size Limits
- Maximum file size: 100 MB
- Files larger than this limit are ignored during indexing

## Architecture

### Components

1. **File Processors**: Extract content from different file types
2. **Document Indexer**: Handle FAISS vector indexing and SQLite metadata storage
3. **Search Agent**: LangGraph-powered intelligent search orchestration
4. **MCP Server**: Model Context Protocol server implementation
5. **CLI Interface**: Rich-powered command-line interface

### Storage

- **Vector Store**: FAISS index stored in `~/.enhanced_finder/vectors/`
- **Metadata**: SQLite database in `~/.enhanced_finder/metadata.db`
- **Configuration**: Stored in application config directory

## Development

### Running Tests
```bash
pytest
```

### Code Formatting
```bash
black enhanced_finder/
ruff enhanced_finder/
```

### Project Structure
```
enhanced_finder/
├── __init__.py          # Package initialization
├── config.py            # Configuration management
├── file_processors.py   # File content extraction
├── indexer.py          # Vector indexing and search
├── agents.py           # LangGraph agent orchestration
├── mcp_server.py       # MCP server implementation
├── cli.py              # Command-line interface
└── main.py             # Entry point
```

## Performance

- **Indexing Speed**: ~100-500 files per minute (depending on file size and type)
- **Search Speed**: Sub-second search results for most queries
- **Memory Usage**: ~200-500 MB for typical document collections
- **Storage**: ~1-5 MB per 1000 documents (varies by content)

## Troubleshooting

### Common Issues

1. **No search results**: Run `better-finder index --full` to rebuild the index
2. **Out of memory**: Reduce `max_file_size_mb` in configuration
3. **Slow indexing**: Check that paths don't include system directories

### Debug Information

```bash
# View current statistics
better-finder stats

# Check configuration
better-finder config list
```

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## Future Enhancements

- [ ] Real-time file monitoring with automatic reindexing
- [ ] Web interface for remote access
- [ ] Integration with cloud storage (Google Drive, Dropbox)
- [ ] Advanced query language support
- [ ] Machine learning-based relevance ranking
- [ ] OCR support for image-based documents
- [ ] Duplicate file detection
- [ ] File preview generation