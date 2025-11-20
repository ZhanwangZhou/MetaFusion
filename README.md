# MetaFusion: Distributed Metadata and Vector Fusion Store

## Overview

MetaFusion is a distributed photo storage and search system that combines metadata filtering with vector similarity search for efficient image retrieval.

**New Feature**: 🎉 Search Method Comparison - Compare MetaFusion, Vector-only, and Metadata-only search approaches!

## Quick Start

### Start Leader Node

```shell
python main.py leader
```

or with custom settings:

```shell
python main.py leader --host <leader_host> --port <leader_port> --base_dir <base_dir> --model_name <model_name> --device <device>
```

### Start Follower Node

```shell
python main.py follower --port 9000
```

or with custom settings:

```shell
python main.py follower --host <follower_host> --port <follower_port> --leader_host <leader_host> --leader_port <leader_port>
```

## Available Commands

Once the leader node is running, you can use the following commands:

| Command | Description | Example |
|---------|-------------|---------|
| `ls` | List all follower nodes | `ls` |
| `upload <path>` | Upload a single image | `upload photo.jpg` |
| `mass_upload <dir>` | Upload all images in a directory | `mass_upload ./photos` |
| `search <prompt>` | MetaFusion search (default) | `search a beach photo` |
| `search_metadata <prompt>` | Metadata-only search | `search_metadata photo in 2023` |
| `search_vector <prompt>` | Vector-only search (all silos) | `search_vector sunset` |
| `search_metafusion <prompt>` | MetaFusion search | `search_metafusion cat photo` |
| `compare <prompt>` | Compare all three methods | `compare mountain in winter` |
| `get <dir> <prompt>` | Search and download images | `get ./output sunset` |
| `clear` | Clear all data | `clear` |
| `help` | Show all commands | `help` |
| `exit` / `quit` | Exit the program | `exit` |

## Search Method Comparison

MetaFusion now supports comparing three different search approaches:

### 1. **MetaFusion Search** (Metadata + Vector)
- Filters candidate silos using metadata (time, location, tags)
- Performs vector search only on filtered silos
- **Best for**: Balancing efficiency and accuracy

### 2. **Vector-Only Search**
- Searches across all follower nodes using vector similarity
- No metadata filtering
- **Best for**: Maximum recall, ensuring no relevant images are missed

### 3. **Metadata-Only Search**
- Uses only metadata (timestamps, GPS, tags) for filtering
- Performed on leader node only, no vector computation
- **Best for**: Fastest search when metadata is sufficient

### Quick Comparison Test

```bash
# In the leader terminal
> compare a photo taken in New York in summer 2023
```

This will automatically:
1. Run all three search methods
2. Compare performance metrics
3. Show search space reduction
4. Display top results from each method

### Using the Test Script

```bash
python test_search_comparison.py
```

Select option 1 for a comprehensive comparison test.

## Documentation

- 📘 **[Quick Start Guide](QUICK_START_COMPARISON.md)** - Get started in 5 minutes
- 📖 **[Detailed Comparison Guide](SEARCH_COMPARISON_GUIDE.md)** - In-depth usage and evaluation metrics
- 🔧 **[Update Notes](SEARCH_COMPARISON_UPDATE.md)** - Technical details of the new features

## Key Features

- ✅ Distributed architecture with leader-follower pattern
- ✅ Metadata-based pre-filtering for efficient search
- ✅ Vector similarity search using CLIP embeddings
- ✅ Three search modes: MetaFusion, Vector-only, Metadata-only
- ✅ Built-in comparison tools for evaluating search methods
- ✅ Automatic EXIF metadata extraction
- ✅ Scalable to multiple follower nodes (silos)

## System Requirements

- Python 3.10+
- PostgreSQL database
- Dependencies: See `requirements.txt`

## Architecture

```
┌─────────────────────────────────────────────────┐
│               Leader Node                        │
│  - Metadata Database (PostgreSQL)               │
│  - Query Processing & Filtering                 │
│  - Result Aggregation                           │
└─────────────┬───────────────────────────────────┘
              │
    ┌─────────┼─────────┐
    │         │         │
    ▼         ▼         ▼
┌────────┐ ┌────────┐ ┌────────┐
│Follower│ │Follower│ │Follower│
│(Silo 0)│ │(Silo 1)│ │(Silo 2)│
│        │ │        │ │        │
│Vector  │ │Vector  │ │Vector  │
│Index   │ │Index   │ │Index   │
└────────┘ └────────┘ └────────┘
```

## Performance

Example comparison results:

```
【Performance Comparison】
Method                   Time(s)          Results
--------------------------------------------------
Metadata Only           0.032           45
Vector Only             5.234           128
MetaFusion             5.156           87

【Result Analysis】
MetaFusion vs Vector Only: Search space reduced by 32.0%
```

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]

