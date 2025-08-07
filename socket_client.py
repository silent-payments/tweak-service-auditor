"""
Socket-based RPC client for Esplora Cake and similar services
"""
import json
import socket
import asyncio
from typing import Dict, Any, Tuple


class Connection:
    """Socket-based RPC connection for Esplora Cake"""
    
    def __init__(self, addr: Tuple[str, int]):
        self.s = socket.create_connection(addr)
        self.f = self.s.makefile('r')
        self.id = 0

    def call(self, method: str, *args) -> Dict[str, Any]:
        """Make a synchronous RPC call"""
        req = {
            'id': self.id,
            'method': method,
            'params': list(args),
        }
        msg = json.dumps(req) + '\n'
        self.s.sendall(msg.encode('ascii'))
        self.id += 1
        return json.loads(self.f.readline())
    
    def close(self):
        """Close the connection"""
        if hasattr(self, 'f'):
            self.f.close()
        if hasattr(self, 's'):
            self.s.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class AsyncConnection:
    """Async wrapper for socket-based RPC connection"""
    
    def __init__(self, addr: Tuple[str, int]):
        self.addr = addr
        self.connection = None
    
    async def __aenter__(self):
        # Run the synchronous connection creation in thread pool
        loop = asyncio.get_event_loop()
        self.connection = await loop.run_in_executor(None, Connection, self.addr)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.connection:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.connection.close)
    
    async def call(self, method: str, *args) -> Dict[str, Any]:
        """Make an async RPC call"""
        if not self.connection:
            raise RuntimeError("Connection not established")
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.connection.call, method, *args)
