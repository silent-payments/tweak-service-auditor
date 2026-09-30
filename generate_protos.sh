#!/usr/bin/env bash
# Generate Python protobuf code from proto/ definitions into pb/
set -e

PYTHON_BIN="${PYTHON:-python3}"
if ! $PYTHON_BIN -c "import grpc_tools.protoc" 2>/dev/null; then
    if python -c "import grpc_tools.protoc" 2>/dev/null; then
        PYTHON_BIN="python"
    elif command -v pyenv &>/dev/null && [ -x "$(pyenv which python)" ]; then
        PYTHON_BIN="$(pyenv which python)"
    fi
fi

mkdir -p pb
$PYTHON_BIN -m grpc_tools.protoc -Iproto --python_out=pb --grpc_python_out=pb proto/indexing_server.proto proto/oracle_service.proto

touch pb/__init__.py
if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' 's/import indexing_server_pb2 as indexing__server__pb2/from . import indexing_server_pb2 as indexing__server__pb2/' pb/oracle_service_pb2_grpc.py
else
    sed -i 's/import indexing_server_pb2 as indexing__server__pb2/from . import indexing_server_pb2 as indexing__server__pb2/' pb/oracle_service_pb2_grpc.py
fi

echo "Protobuf files successfully generated in pb/"
