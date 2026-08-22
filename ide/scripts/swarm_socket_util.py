import socket
import struct
import io
import torch
import time

def send_tensor_socket(tensor, sock):
    """テンソルをバイナリ化してソケットに送信する"""
    buffer = io.BytesIO()
    torch.save(tensor, buffer)
    data = buffer.getvalue()
    size_bytes = struct.pack("!I", len(data))
    sock.sendall(size_bytes)
    sock.sendall(data)

def recv_tensor_socket(sock, device):
    """ソケットからバイナリを受け取りテンソルに復元する"""
    def recvall(n):
        data = bytearray()
        while len(data) < n:
            packet = sock.recv(n - len(data))
            if not packet:
                return None
            data.extend(packet)
        return data

    size_bytes = recvall(4)
    if not size_bytes:
        return None
    size = struct.unpack("!I", size_bytes)[0]
    data = recvall(size)
    if not data:
        return None
    buffer = io.BytesIO(data)
    tensor = torch.load(buffer, map_location=device)
    return tensor

def create_server_socket(port):
    """サーバーソケットを作成して待機する"""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('127.0.0.1', port))
    server.listen(1)
    return server

def connect_to_server(port, retries=10, delay=1):
    """クライアントソケットを作成してサーバーに接続する"""
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    for _ in range(retries):
        try:
            client.connect(('127.0.0.1', port))
            return client
        except ConnectionRefusedError:
            time.sleep(delay)
    raise ConnectionError(f"Failed to connect to port {port}")
