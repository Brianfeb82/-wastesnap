"""GET /api/health"""
import json

def handler(request):
    class Response:
        def __init__(self):
            self.status_code = 200
            self.body = json.dumps({"status": "ok"})
            self.headers = {"Content-Type": "application/json"}
    return Response()
