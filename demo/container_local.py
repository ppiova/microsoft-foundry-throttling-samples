"""Local Docker entry point; publish port 8765 on host loopback only."""
from server import Handler, ThreadingHTTPServer

if __name__ == '__main__':
    # Docker needs a container-wide listener. Handler retains loopback Host
    # and Origin validation; compose.yaml restricts the published host port.
    httpd = ThreadingHTTPServer(('0.0.0.0', 8765), Handler)
    print('Local container UI: http://127.0.0.1:8765', flush=True)
    httpd.serve_forever()
