# Silent Payments Tweak Service Auditor

A Python tool for auditing Silent Payments indexer tweak services to determine which services are producing the most accurate tweak data.

## Recent Updates

**Latest: BlindBit gRPC Support + Test Data Framework**
- **🚀 BlindBit gRPC Integration**: Native gRPC support with high-performance streaming for efficient bulk block range processing
- **📊 Test Data Framework**: Compare services against canonical reference data with automatic validation and storage capabilities  
- **⚡ Enhanced Performance**: Hybrid processing approach - gRPC streaming for BlindBit, optimized batching for other services
- **🔧 Smart Configuration**: Auto-detection of service pairs, filter mismatch warnings, and intelligent fallback handling
- **🛠️ New CLI Features**: `--store_test` flag for creating test data, `--ignore-filter-mismatch` for bypassing validation warnings

## Outline
- [Recent Updates](#recent-updates)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
  - [Test Data Framework](#test-data-framework)
- [Usage](#usage)
- [Core Capabilities](#core-capabilities)
- [Output Examples](#output-examples)
- [JSON Output](#json-output)
- [Architecture](#architecture)
- [Logging and Error Handling](#logging-and-error-handling)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)

## Features

- **Multi-service support**: Audit multiple indexing services simultaneously
- **Flexible connection methods**: Support for HTTP, RPC, socket-based RPC, and gRPC services
- **Extensible architecture**: Easy to add new service implementations - blindbit-oracle, blindbit-grpc, esplora-cake, bitcoin-core, electrs supported
- **Pairwise comparison analysis**: Compare specific service pairs with detailed matching statistics
- **Range auditing**: Audit single blocks or ranges of blocks
- **Detailed reporting**: Comprehensive results with statistics and comparisons
- **Configuration management**: JSON-based configuration with validation
- **JSON output**: Export audit results to structured JSON files
- **Test data framework**: Compare against canonical reference data with automatic validation
- **High-performance streaming**: gRPC streaming support for efficient bulk block processing

## Installation

1. Clone or download this repository
2. Install dependencies:
   ```bash
   just init
   ```

## Quick Start

1. **Edit the configuration** (`sample.config.json`) to add your actual service endpoints

2. **Audit a single block**:
   ```bash
   python main.py block 800000
   ```

3. **Audit a range of blocks**:
   ```bash
   python main.py range 800000 800010
   ```

4. **Compare against test data** (using included reference blocks):
   ```bash
   # Test bitcoin-core against reference data for block 850000, assumes test_data/block_850000.json exist
   python main.py block 850000
   ```

## Configuration

The auditor uses a JSON configuration file to define the indexing services to audit. Review sample.config.json for guidance:

### Configuration Format

The configuration file defines services and optional pairwise comparison groups:

```json
{
  "services": [
    {
      "name": "http-service",
      "service_type": "http",
      "endpoint": "https://api.yourservice.com",
      "headers": {
        "User-Agent": "TweakServiceAuditor/1.0"
      },
      "timeout": 5,
      "active": true,
      "cookie_file": "/path/to/.cookie",
      "requests_per_second": 100
    },
    {
      "name": "bitcoin-core-local",
      "service_type": "rpc",
      "endpoint": "http://127.0.0.1:8332",
      "auth": {
        "username": "your_rpc_user",
        "password": "your_rpc_password"
      },
      "timeout": 5,
      "active": true,
      "cookie_file": "/path/to/.cookie",
      "requests_per_second": 200,
      "filter_spent": false,
      "dust_limit": 0
    }
  ],
  "service_pairs": [
    {
      "name": "http-vs-rpc",
      "service1": "http-service",
      "service2": "bitcoin-core-local",
      "active": true
    }
  ]
}
```

### Configuration Fields

**Service Configuration:**
- `name`: Unique identifier for the service
- `service_type`: "http", "rpc", or "socket_rpc" 
- `endpoint`: Service URL/endpoint (for HTTP/RPC) or "host:port" (for socket_rpc)
- `host`: Host address (optional, for socket_rpc services)
- `port`: Port number (optional, for socket_rpc services)
- `auth`: Authentication credentials (optional)
- `headers`: Custom HTTP headers (optional, HTTP/RPC only)
- `timeout`: Request timeout in seconds (default: 60)
- `active`: Whether the service is enabled for auditing (default: true)
- `cookie_file`: Path to a cookie file for authentication (optional, for Bitcoin Core and similar)
- `requests_per_second`: Maximum requests per second to this service (optional, default: 200)
- `filter_spent`: Whether to filter spent outputs in Bitcoin Core RPC calls (optional, for bitcoin-core service type)
- `dust_limit`: Dust limit threshold for Bitcoin Core RPC calls (optional, default: 0)

**Service Pair Configuration:**
- `name`: Unique identifier for the comparison pair
- `service1`: Name of first service to compare
- `service2`: Name of second service to compare  
- `active`: Whether this pair comparison is enabled (default: true)

### Service Types

#### HTTP Services
Standard HTTP REST API endpoints:
```json
{
  "name": "my-http-service",
  "service_type": "http",
  "endpoint": "https://api.yourservice.com",
  "headers": {"Authorization": "Bearer token"},
  "timeout": 30,
  "active": true,
  "cookie_file": "/path/to/.cookie",
  "requests_per_second": 200
}
```

#### RPC Services  
JSON-RPC over HTTP:
```json
{
  "name": "bitcoin-core",
  "service_type": "rpc",
  "endpoint": "http://127.0.0.1:8332",
  "auth": {"username": "user", "password": "pass"},
  "timeout": 60,
  "active": true,
  "cookie_file": "/path/to/.cookie",
  "requests_per_second": 100
}
```

#### Socket RPC Services (Esplora Cake)
Direct socket connections for Esplora Cake and similar services:
```json
{
  "name": "esplora-cake",
  "service_type": "socket_rpc", 
  "endpoint": "127.0.0.1:60601",
  "timeout": 30,
  "active": true,
  "requests_per_second": 200
}
```

#### gRPC Services (BlindBit)
High-performance gRPC connections with streaming support:
```json
{
  "name": "blindbit-grpc",
  "service_type": "grpc",
  "endpoint": "127.0.0.1:50051",
  "timeout": 600,
  "active": true,
  "requests_per_second": 150,
  "dust_limit": 0
}
```

#### Test Data Services
Compare against canonical reference data stored locally:
```json
{
  "name": "test_data",
  "service_type": "test_data",
  "endpoint": "local",
  "active": true
}
```

### Test Data Framework

The auditor includes a comprehensive test data framework for validating services against canonical reference data:

#### Available Test Blocks
The `test_data/` directory contains reference data for various block ranges:

**Mainnet Blocks:**
- `800000-800004`: Mainnet reference blocks for production validation

**Signet Blocks:**
- `200000-200002`: Early signet blocks with moderate activity


#### Test Data Configuration Example

```json
{
  "services": [
    {
      "name": "bitcoin-core",
      "service_type": "rpc",
      "endpoint": "http://127.0.0.1:38332",
      "cookie_file": "~/work/bitcoin/signet/.cookie",
      "active": true,
      "filter_spent": false,
      "dust_limit": 0
    }
  ],
  "service_pairs": [
    {
      "name": "bitcoin_vs_test",
      "service1": "bitcoin-core", 
      "service2": "test_data",
      "active": true
    }
  ]
}
```

**Note**: When a `service_pairs` entry references a service named `test_data` that doesn't exist in the `services` list, the auditor will automatically create a test_data service if test data files are available.

#### Creating New Test Data

```bash
# Store results from bitcoin-core as canonical test data
python main.py block 850000 --store_test bitcoin-core

# Store range results (creates multiple test files)
python main.py range 850000 850002 --store_test bitcoin-core
```

### Defaults
- `timeout`: 60 seconds if not specified
- `active`: true if not specified
- `requests_per_second`: 200 if not specified

## Usage

The `main.py` script provides a comprehensive command-line interface for auditing Silent Payments tweak services.

### Command Line Interface

```bash
python main.py [options] <command> [sub-options]
```

### Commands

#### Configuration Management

```bash
# List all configured services and their status
python main.py config --list-services

# Validate current configuration
python main.py config --validate-config
```

#### Single Block Auditing

```bash
# Audit single block
python main.py block 800000

# Audit with detailed tweak hash output
python main.py block 800000 --detailed

# Save results to JSON file
python main.py block 800000 --output results.json

# Audit with custom config file
python main.py --config my-config.json block 800000 
```

#### Range Auditing

```bash
# Audit range of blocks
python main.py range 800000 800010

# Audit range with detailed output and save results
python main.py range 800000 800010 --detailed --output range_results.json

# Audit large range with verbose logging
python main.py range 800000 801000 --output large_audit.json
```

### Global Options

- `--config, -c`: Specify configuration file path (default: config.json)
- `--verbose, -v, -vv`: Enable verbose logging for debugging
- `--detailed, -d`: Show detailed results including individual tweak hashes
- `--output, -o`: Save results to JSON file for further analysis
- `--store_test [service_name]`: Store audit results as canonical test data for future comparisons
- `--ignore-filter-mismatch`: Ignore filter configuration mismatch warnings between services

### Services Setup Reference

#### bitcoin core
```sh
# https://github.com/Sjors/bitcoin/pull/86
cd <src path>/bitcoin
./build/bin/bitcoin node -bip352index
```

##### cake esplora/electrs
```sh
# https://github.com/cake-tech/blockstream-electrs/tree/cake-update-v1
cd <src path>/blockstream-electrs
./target/release/electrs -vvv --network signet --db-dir <data path>/cake-electrs --index-unspendables --skip-mempool --blocks-dir <data path>/bitcoin/signet/blocks --daemon-dir <data path>/bitcoin --sp-begin-height 100000 --jsonrpc-import
```

#### blindbit-oracle
```sh
# https://github.com/setavenger/blindbit-oracle
cd <src path>/blindbit-oracle
go run ./src
```

## Core Capabilities

### Service Auditing
- **Multi-service support**: Simultaneously query multiple indexing services for tweak data
- **Service validation**: Automatic validation of service configurations and connectivity
- **Error handling**: Graceful handling of service failures while continuing with remaining services
- **Performance tracking**: Request timing and success rate monitoring

### Comparison Analysis
- **Cross-service comparison**: Identify matching and unique tweaks across all services
- **Pairwise analysis**: Detailed comparison between specific service pairs
- **Match percentage calculation**: Statistical analysis of service agreement
- **Unique tweak identification**: Highlight tweaks found by only one service

### Data Processing
- **Normalized data format**: Convert all service responses to standardized `TweakData` format
- **Block range processing**: Efficiently process single blocks or ranges of blocks
- **Aggregated reporting**: Summary statistics across multiple blocks and services
- **JSON export**: Export all results in structured JSON format for further analysis

### Real-time Monitoring
- **Live audit results**: Real-time display of audit progress and results
- **Detailed logging**: Configurable logging levels for debugging and monitoring
- **Service status tracking**: Monitor which services succeed or fail during audits

## Output Examples

### Single Block Audit

```
=== Audit Results for Block 800000 ===
Services: 2/3 successful

Tweak counts by service:
  service-a: 15 tweaks
  service-b: 12 tweaks

Matching tweaks across all services: 10

Unique tweaks by service:
  service-a: 5 unique tweaks
  service-b: 2 unique tweaks

=== Pairwise Service Comparisons ===

service-a-vs-service-b (service-a vs service-b):
  service-a: 15 tweaks
  service-b: 12 tweaks
  Matching tweaks: 10
  service-a unique: 5
  service-b unique: 2
  Match percentage: 76.9%

Failed services:
  service-c: Connection timeout
```

### Range Audit

```
=== Range Audit Results (Blocks 800000-800010) ===
Total blocks processed: 11

Summary by service:
  service-a:
    Total tweaks: 150
    Blocks processed: 11
    Failures: 0
  service-b:
    Total tweaks: 140
    Blocks processed: 10
    Failures: 1

=== Pairwise Comparison Summary ===

service-a-vs-service-b (service-a vs service-b):
  Blocks processed: 10
  Total matching tweaks: 120
  Total service-a unique: 25
  Total service-b unique: 15
  Overall match percentage: 75.0%
```

## JSON Output

When using `--output`, results are saved in structured JSON format for further analysis:

### Single Block Output
```json
{
  "block_height": 800000,
  "timestamp": 1703123456.789,
  "services": 3,
  "successful_services": 2,
  "tweak_counts": {
    "service-a": 15,
    "service-b": 12
  },
  "matching_tweaks": 10,
  "non_matching_by_service": {
    "service-a": 5,
    "service-b": 2
  },
  "pairwise_comparisons": [
    {
      "pair_name": "service-a-vs-service-b",
      "service1_name": "service-a",
      "service2_name": "service-b",
      "service1_tweaks": 15,
      "service2_tweaks": 12,
      "matching_tweaks": 10,
      "service1_unique": 5,
      "service2_unique": 2,
      "match_percentage": 76.9
    }
  ]
}
```

### Range Audit Output
```json
{
  "start_block": 800000,
  "end_block": 800010,
  "total_blocks_audited": 11,
  "summary_by_service": {
    "service-a": {
      "total_tweaks": 150,
      "blocks_processed": 11,
      "failures": 0
    },
    "service-b": {
      "total_tweaks": 140,
      "blocks_processed": 10,
      "failures": 1
    }
  },
  "block_results": [
    {
      "block_height": 800000,
      "tweak_counts": {"service-a": 15, "service-b": 12},
      "matching_tweaks": 10,
      "non_matching_by_service": {"service-a": 5, "service-b": 2},
      "pairwise_comparisons": [...]
    }
  ]
}
```

## Architecture

### Core Components

1. **Main CLI** (`main.py`): Complete command-line interface with audit orchestration, result formatting, and JSON export
2. **Models** (`models.py`): Data structures for tweaks, service configurations, audit results, and pairwise comparisons
3. **Auditor** (`auditor.py`): Main audit logic for single blocks and block ranges
4. **Service Interface** (`service_interface.py`): Abstract base classes for HTTP and RPC services
5. **Service Implementations** (`service_implementations.py`): Concrete implementations for specific services
6. **Configuration** (`config.py`): Configuration management, validation, and service pair handling

### Extending with New Services

To add support for a new indexing service:

1. **Create a new service implementation** extending either `HTTPIndexService` or `RPCIndexService`
2. **Implement required methods**:
   - `_build_url()` or `_build_rpc_payload()`: Construct service-specific requests
   - `_normalize_response()`: Convert service response to standard `TweakData` format

## Logging and Error Handling

### Logging Levels
- **INFO level**: Basic audit progress and results (use `-v`)
- **DEBUG level**: Detailed request/response information (use `-vv`)
- **ERROR level**: Service failures and errors

### Error Handling
The auditor gracefully handles:
- Network timeouts and connection failures
- Invalid service responses
- Configuration validation errors
- Individual service failures (continues with other services)
- Malformed JSON responses

## Development

### Project Structure
```
tweak-service-auditor/
├── main.py                    # CLI entry point and audit orchestration
├── auditor.py                 # Core audit logic and service coordination
├── models.py                  # Data models and result structures
├── service_interface.py       # Abstract service interfaces
├── service_implementations.py # Concrete service implementations
├── config.py                  # Configuration management and validation
├── requirements.txt           # Python dependencies
├── justfile                   # just
├── config.json                # Service configuration (user-created)
└── README.md                  # This documentation
```

### Testing Your Setup

```bash
# List configured services
just services

# Test audit with verbose logging
just block 800000 -v
```

## Contributing

1. Follow the existing code structure and patterns
2. Add appropriate error handling and logging
3. Update this README when adding new features
4. Test with multiple service types and configurations

## License

This project is provided as-is for auditing Silent Payments indexer services.
