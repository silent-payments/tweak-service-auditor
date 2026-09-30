# Silent Payments Tweak Service Auditor

A Python tool for auditing Silent Payments indexer tweak services to determine which services are producing the most accurate tweak data.

## Outline
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
  - [3-Tier Resolution Hierarchy](#3-tier-resolution-hierarchy)
  - [Supported Environment Variables](#supported-environment-variables)
  - [Test Data Framework](#test-data-framework)
- [Usage](#usage)
- [Testing](#testing)
- [Architecture](#architecture)
- [Contributing](#contributing)
- [License](#license)

## Installation

1. Clone or download this repository
2. Install dependencies:
   ```bash
   just init
   ```
   *(Or manually create a virtual environment and run `pip install -r requirements.txt`)*

---

## Quick Start

### Option A: Zero-Config via Environment Variables (Recommended)

Set the endpoints for the services you are running and audit immediately without creating any config files:

```bash
# Export the endpoints of your running daemons
export RBITCOIN_ENDPOINT="127.0.0.1:51001"
export BLINDBIT_GRPC_ENDPOINT="127.0.0.1:51051"

# Audit a single Signet block
just block 200000

# Audit a range of blocks
just range 200000 200010
```

### Option B: Using a Configuration File

1. Copy the sample configuration:
   ```bash
   just make-config   # Copies sample.config.json to config.json
   ```
2. Inspect or customize `config.json` (it supports `${VAR:-default}` environment substitutions).
3. Run the audit:
   ```bash
   just block 200000
   ```

---

## Configuration

The auditor supports a flexible **3-Tier Configuration Hierarchy** that keeps your setup clean and prevents hardcoding private LAN IP addresses into version-controlled files.

### 3-Tier Resolution Hierarchy

1. **Tier 1: Dynamic Environment Override (Highest Priority)**  
   If an environment variable (e.g. `RBITCOIN_ENDPOINT`) is set in your shell, it dynamically overrides the endpoint configured in `config.json` and activates that service automatically.
2. **Tier 2: Environment Variable Expansion in JSON**  
   All string values in `config.json` expand environment variables using `${VAR:-default}` syntax. For example:
   ```json
   "endpoint": "${RBITCOIN_ENDPOINT:-127.0.0.1:51001}"
   ```
3. **Tier 3: Pure Environment Auto-Discovery (Zero-Config Fallback)**  
   If no `config.json` file is present, the auditor inspects active environment variables, automatically creates service configs for them, and pairs them for differential auditing.

### Supported Environment Variables

| Variable | Target Service | Default Protocol / Port |
| :--- | :--- | :--- |
| `RBITCOIN_ENDPOINT` | `rbitcoin` (`rbitcoin-node`) | Socket RPC (`127.0.0.1:51001`) |
| `BLINDBIT_GRPC_ENDPOINT` | `blindbit-grpc` | gRPC (`127.0.0.1:51051`) |
| `BLINDBIT_HTTP_ENDPOINT` | `blindbit` (`blindbit-oracle`) | HTTP REST (`http://127.0.0.1:8000/tweak-index`) |
| `ESPLORA_ENDPOINT` | `esplora-cake` | Socket RPC (`127.0.0.1:60601`) |
| `ELECTRS_ENDPOINT` | `electrs` | Socket RPC (`127.0.0.1:50001`) |
| `BITCOIN_RPC_ENDPOINT` | `bitcoin` (Bitcoin Core) | HTTP JSON-RPC (`http://127.0.0.1:38332`) |

### Configuration File Format (`sample.config.json`)

```json
{
  "services": [
    {
      "name": "rbitcoin",
      "service_type": "socket_rpc",
      "endpoint": "${RBITCOIN_ENDPOINT:-127.0.0.1:51001}",
      "active": true,
      "timeout": 30
    },
    {
      "name": "blindbit-grpc",
      "service_type": "grpc",
      "endpoint": "${BLINDBIT_GRPC_ENDPOINT:-127.0.0.1:51051}",
      "active": true,
      "timeout": 60,
      "requests_per_second": 150,
      "dust_limit": 0
    },
    {
      "name": "blindbit",
      "service_type": "http",
      "endpoint": "${BLINDBIT_HTTP_ENDPOINT:-http://127.0.0.1:8000/tweak-index}",
      "headers": {
        "User-Agent": "TweakServiceAuditor/1.0"
      },
      "active": false,
      "requests_per_second": 100
    }
  ],
  "service_pairs": [
    {
      "name": "rbitcoin-vs-blindbit-grpc",
      "service1": "rbitcoin",
      "service2": "blindbit-grpc",
      "active": true
    }
  ]
}
```

### Test Data Framework

The auditor includes reference test data for validating services offline against canonical blocks:

- `test_data/block_200000.json` - `block_200002.json`: Signet reference blocks
- `test_data/block_850000.json` - `block_850003.json`: Mainnet reference blocks

```bash
# Compare a running service against canonical reference data
just block 200000
```

---

## Usage

### Commands

#### Check Configured Services
```bash
just services
# Or with explicit config:
python main.py config --list
```

#### Validate Configuration
```bash
just validate
```

#### Audit a Single Block
```bash
# Standard summary
just block 200000

# Detailed tweak hash output and verbose logging
just block -d -v 200000

# Save structured results to JSON
just block -d -o results.json 200000
```

#### Audit a Range of Blocks
```bash
# Audit a 10-block range
just range 200000 200010

# Audit range with detailed output and stream to file
just range -d -vv 200000 200010 -o range_summary.json
```

---

## Testing

The project uses a unified test suite that separates offline unit testing from live endpoint verification using the presence of environment variables:

```bash
# 1. Run offline unit tests (runs in <0.07s; skips unconfigured live endpoints)
just test

# 2. Run unit tests AND verify live rbitcoin connection
RBITCOIN_ENDPOINT="127.0.0.1:51001" just test -v

# 3. Run unit tests AND verify both rbitcoin and blindbit-grpc
RBITCOIN_ENDPOINT="127.0.0.1:51001" BLINDBIT_GRPC_ENDPOINT="127.0.0.1:51051" just test -v
```

---

## Services Setup Reference

#### rbitcoin-node
```bash
# https://github.com/reardencode/rbitcoin
./target/release/rbitcoin-node --datadir /mnt/data/rbitcoin/signet --sptweaks --network signet --electrum-listen 0.0.0.0:51001 --shindex
```

#### blindbit-oracle
```bash
# https://github.com/setavenger/blindbit-oracle
go run ./src
```

#### cake esplora/electrs
```bash
# https://github.com/cake-tech/blockstream-electrs/tree/cake-update-v1
./target/release/electrs -vvv --network signet --db-dir <data path>/cake-electrs --index-unspendables --skip-mempool --blocks-dir <data path>/bitcoin/signet/blocks --daemon-dir <data path>/bitcoin --sp-begin-height 100000 --jsonrpc-import
```

#### bitcoin core
```bash
# https://github.com/Sjors/bitcoin/pull/86
./build/bin/bitcoin node -bip352index
```

---

## Architecture

1. **CLI Orchestration** (`main.py`): Command dispatching, argument parsing, output formatting.
2. **Auditor Engine** (`auditor.py`): Concurrent block querying, consensus calculation, and range streaming.
3. **Configuration Manager** (`config.py`): 3-tier hierarchy, environment variable expansion, and auto-pairing.
4. **Service Drivers** (`service_implementations.py`): Concrete drivers for `RBitcoinService`, `BlindBitGRPCService`, `BitcoinCoreRPCService`, and `ElectrsRPCService`.
5. **Protobuf Schemas** (`proto/`): Formal IDL schemas compiled into `pb/` via `generate_protos.sh`.

---

## License

This project is provided as-is for auditing Silent Payments indexer services.
