from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

endpoints = {}
generic_handler = None

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def handle_request(path: str, request: Request):
    """Route all requests to registered endpoints."""
    params = dict(request.query_params)
    body = await request.body()
    
    request_data = {
        'method': request.method,
        'endpoint': path,
        'params': params,
        'body': body.decode() if body else None
    }
    
    # Call generic handler first if it exists
    if generic_handler:
        generic_result = generic_handler(request_data)
        if hasattr(generic_result, '__await__'):
            generic_result = await generic_result
        # If generic handler returns a response, use it
        if generic_result is not None:
            return generic_result
    
    # Then call specific endpoint if it exists
    if path in endpoints:
        result = endpoints[path](request_data)
        # Handle both sync and async endpoints
        if hasattr(result, '__await__'):
            return await result
        return result
    
    return {"error": "Endpoint not found"}, 404

def start_server(endpoint_dict, host="0.0.0.0", port=8000, handler=None):
    """Start the web server with given endpoints and optional generic handler."""
    global endpoints, generic_handler
    endpoints = endpoint_dict
    generic_handler = handler
    print(f"Starting server on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)

def demo():
    def log_all_requests(request):
        """Generic handler that logs all requests and handles some endpoints."""
        print(f"[{request['method']}] /{request['endpoint']}")
        
        # Handle 'status' endpoint in generic handler
        if request['endpoint'] == 'status':
            return {"status": "ok", "message": "Server is running"}
        
        # Return None to let specific endpoints handle the request
        return None
    
    def hello_endpoint(request):
        return {"message": "Hello, World!"}
    
    demo_endpoints = {
        'hello': hello_endpoint
    }
    
    start_server(demo_endpoints, handler=log_all_requests)

if __name__ == "__main__":
    demo()
