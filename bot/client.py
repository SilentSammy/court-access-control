"""
Auto-generated HTTP client from FastAPI server.

Takes a FastAPI app and endpoint functions, auto-generates:
- Client methods that make HTTP calls
- Function tools for LLM agents
"""
import httpx
import re
from functools import wraps
from inspect import Parameter, Signature
from typing import Callable, Optional
from fastapi import FastAPI

from agents import function_tool, RunContextWrapper


class ToolEnabledHttpClient:
    """Auto-generate HTTP client methods and tools from FastAPI endpoints"""
    
    def __init__(self, app: FastAPI, base_url: str = "http://localhost:8000"):
        """
        Initialize the client.
        
        Args:
            app: FastAPI application instance
            base_url: Base URL of the server (default: http://localhost:8000)
        """
        self.app = app
        self.base_url = base_url
        self.client_methods = {}
        self.tools = {}
        self._route_cache = {}
    
    def _find_route(self, endpoint_func):
        """Find FastAPI route for an endpoint function"""
        for r in self.app.routes:
            if hasattr(r, 'endpoint') and r.endpoint is endpoint_func:
                return r
        return None
    
    def make_client_method(self, endpoint_func) -> Callable:
        """
        Create a client method from a FastAPI endpoint function.
        
        This inspects the route to extract HTTP method, path, and parameters,
        then returns an async function that makes HTTP calls.
        """
        import inspect
        from types import FunctionType
        
        # Find the route for this endpoint
        route = self._find_route(endpoint_func)
        if not route:
            raise ValueError(f"Endpoint {endpoint_func.__name__} not found in app")
        
        # Extract HTTP method and path template
        http_method = list(route.methods)[0] if route.methods else 'GET'
        path_template = route.path
        
        # Extract path parameter names (e.g., {user_id})
        path_params = set(re.findall(r'\{(\w+)\}', path_template))
        
        # Get function name for reference
        func_name = endpoint_func.__name__
        
        # Get original signature
        original_sig = inspect.signature(endpoint_func)
        
        # Create the actual async method closure that captures all needed variables
        async def make_method():
            # This closure captures all variables from the enclosing scope
            async def client_method(**kwargs) -> dict:
                """Auto-generated HTTP client call"""
                try:
                    async with httpx.AsyncClient() as client:
                        # Build URL: format path with path parameters
                        url_params = {k: v for k, v in kwargs.items() if k in path_params}
                        url = self.base_url + path_template.format(**url_params)
                        
                        # Extract body parameters (everything except path params)
                        body_data = {k: v for k, v in kwargs.items() if k not in path_params}
                        
                        # Make HTTP call based on method
                        if http_method == 'GET':
                            response = await client.get(url, params=body_data if body_data else None)
                        elif http_method == 'POST':
                            response = await client.post(url, json=body_data if body_data else None)
                        elif http_method == 'PUT':
                            response = await client.put(url, json=body_data if body_data else None)
                        elif http_method == 'PATCH':
                            response = await client.patch(url, json=body_data if body_data else None)
                        elif http_method == 'DELETE':
                            response = await client.delete(url)
                        else:
                            raise ValueError(f"Unsupported HTTP method: {http_method}")
                        
                        response.raise_for_status()
                        return response.json()
                
                except httpx.HTTPError as e:
                    raise Exception(f"HTTP error calling {func_name}: {e}")
            
            return client_method
        
        # Actually, let's use a simpler approach: just set __signature__ but also ensure
        # the function can accept both positional and keyword arguments by using *args, **kwargs
        # and then converting *args to kwargs based on the signature
        
        @wraps(endpoint_func)
        async def client_method(*args, **kwargs) -> dict:
            """Auto-generated HTTP client call"""
            # Convert positional arguments to keyword arguments using the original signature
            bound_args = original_sig.bind_partial(*args, **kwargs)
            bound_args.apply_defaults()
            kwargs = bound_args.arguments
            
            try:
                async with httpx.AsyncClient() as client:
                    # Build URL: format path with path parameters
                    url_params = {k: v for k, v in kwargs.items() if k in path_params}
                    url = self.base_url + path_template.format(**url_params)
                    
                    # Extract body parameters (everything except path params)
                    # For Pydantic models, unwrap them (pass dict directly, not wrapped in param name)
                    body_data = {}
                    for param_name, param_value in kwargs.items():
                        if param_name not in path_params:
                            # Get parameter annotation to check if it's a Pydantic model
                            param = original_sig.parameters.get(param_name)
                            if param and param.annotation != inspect.Parameter.empty:
                                # Check if annotation is a Pydantic BaseModel
                                try:
                                    from pydantic import BaseModel
                                    if isinstance(param.annotation, type) and issubclass(param.annotation, BaseModel):
                                        # Unwrap Pydantic model: merge its fields into body_data
                                        if isinstance(param_value, dict):
                                            body_data.update(param_value)
                                        else:
                                            # If it's already a Pydantic model instance, convert to dict
                                            body_data.update(param_value.model_dump())
                                        continue
                                except:
                                    pass
                            # Non-Pydantic parameter, add as-is
                            body_data[param_name] = param_value
                    
                    # Make HTTP call based on method
                    if http_method == 'GET':
                        response = await client.get(url, params=body_data if body_data else None)
                    elif http_method == 'POST':
                        response = await client.post(url, json=body_data if body_data else None)
                    elif http_method == 'PUT':
                        response = await client.put(url, json=body_data if body_data else None)
                    elif http_method == 'PATCH':
                        response = await client.patch(url, json=body_data if body_data else None)
                    elif http_method == 'DELETE':
                        response = await client.delete(url)
                    else:
                        raise ValueError(f"Unsupported HTTP method: {http_method}")
                    
                    response.raise_for_status()
                    return response.json()
            
            except httpx.HTTPError as e:
                raise Exception(f"HTTP error calling {func_name}: {e}")
        
        # Set the signature so introspection tools (like function_tool) see the correct parameters
        client_method.__signature__ = original_sig
        
        return client_method
    
    def register_endpoint(self, endpoint_func) -> None:
        """Register a single FastAPI endpoint function as a client method and tool"""
        func_name = endpoint_func.__name__
        client_method = self.make_client_method(endpoint_func)
        self.client_methods[func_name] = client_method
        
        # Create a FunctionTool from the client method
        tool = function_tool()(client_method)
        self.tools[func_name] = tool

    def register_endpoints(self, endpoint_funcs: list) -> None:
        """
        Auto-generate client methods and tools for endpoint functions.
        
        Args:
            endpoint_funcs: List of FastAPI endpoint functions
        """
        for func in endpoint_funcs:
            self.register_endpoint(func)
    
    def get_all_tools(self) -> list:
        """Return all generated tools for use in Agent"""
        return list(self.tools.values())
    
    def get_client_method(self, name: str) -> Optional[Callable]:
        """Get a specific client method by name"""
        return self.client_methods.get(name)
    
    def get_tool(self, name: str) -> Optional:
        """Get a specific tool by name"""
        return self.tools.get(name)


def wrap_tool(
    original_method,
    injected_params: dict,
    exposed_params: dict[str, type],
    new_name: str = None,
    new_description: str = None
):
    """
    Wrap an HTTP client method to auto-inject parameters and expose only selected parameters.
    
    This creates a new FunctionTool that wraps an existing HTTP client method, automatically
    injecting certain parameters (like user_id) while exposing others to the LLM.
    
    Args:
        original_method: The HTTP client method to wrap (async callable)
        injected_params: Dict of parameters to auto-inject (e.g., {"user_id": "123"})
        exposed_params: Dict of parameter names to types that LLM can modify
                       (e.g., {"name": str, "email": str, "age": int})
        new_name: Optional new name for the wrapped tool. Defaults to {method}_{injected_key}
        new_description: Optional new description. Defaults to "Personal version of {method}"
    
    Returns:
        A FunctionTool that the LLM can call with only exposed_params visible
    
    Example:
        update_my_profile = wrap_tool(
            original_method=http_client.get_client_method("update_user"),
            injected_params={"user_id": user_id},
            exposed_params={"name": str, "email": str, "age": int}
        )
    """
    import inspect
    from pydantic import BaseModel
    
    # Get the original method name and signature
    method_name = original_method.__name__
    original_sig = inspect.signature(original_method)
    
    # Generate default names if not provided
    if new_name is None:
        injected_key = list(injected_params.keys())[0] if injected_params else "personal"
        new_name = f"{method_name}_{injected_key}"
    if new_description is None:
        new_description = f"Personal version of {method_name}"
    
    # Create the wrapper function
    async def wrapped_tool_func(ctx: RunContextWrapper, **kwargs) -> str:
        """Wrapped tool with auto-injected and exposed parameters."""
        
        # Filter kwargs to only include exposed params with non-None values
        filtered_kwargs = {k: v for k, v in kwargs.items() if k in exposed_params and v is not None}
        
        # Start with injected params
        call_params = injected_params.copy()
        
        # Pack parameters into Pydantic model if needed
        for param_name, param in original_sig.parameters.items():
            if param_name not in injected_params:
                param_type = param.annotation
                if param_type != inspect.Parameter.empty:
                    try:
                        if isinstance(param_type, type) and issubclass(param_type, BaseModel):
                            # Pack all exposed params into the Pydantic model
                            model_data = {}
                            for exposed_param in exposed_params:
                                if exposed_param in filtered_kwargs:
                                    model_data[exposed_param] = filtered_kwargs[exposed_param]
                                else:
                                    model_data[exposed_param] = None
                            call_params[param_name] = model_data
                            # Remove from filtered_kwargs since we packed them
                            for exposed_param in list(filtered_kwargs.keys()):
                                filtered_kwargs.pop(exposed_param, None)
                            break
                    except TypeError:
                        pass
        
        # Add remaining params (for endpoints without Pydantic models)
        for param_name, param_value in filtered_kwargs.items():
            if param_name not in call_params:
                call_params[param_name] = param_value
        
        # Call the original method
        try:
            result = await original_method(**call_params)
            return f"✓ Success: {result}"
        except Exception as e:
            import traceback
            return f"Error: {type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
    
    # Manually set the function signature with explicit parameters for proper schema generation
    # Note: Using param_type directly (not Optional) to avoid anyOf in schema
    # Parameters will be marked as required but have default None
    sig_params = [
        Parameter('ctx', Parameter.POSITIONAL_OR_KEYWORD, annotation=RunContextWrapper)
    ]
    for param_name, param_type in exposed_params.items():
        sig_params.append(
            Parameter(
                param_name, 
                Parameter.KEYWORD_ONLY, 
                default=None, 
                annotation=param_type
            )
        )
    wrapped_tool_func.__signature__ = Signature(sig_params, return_annotation=str)
    
    # Create and return the FunctionTool
    return function_tool(
        name_override=new_name,
        description_override=new_description
    )(wrapped_tool_func)


if __name__ == "__main__":
    import asyncio
    from server import fastapi_app, get_users, get_user, create_user, update_user, delete_user
    
    async def test_client():
        """Test the auto-generated client"""
        print("=" * 70)
        print("Testing ToolEnabledHttpClient")
        print("=" * 70)
        
        # Create client
        print("\n1. Creating client and registering endpoints...")
        client = ToolEnabledHttpClient(fastapi_app, base_url="http://localhost:8000")
        
        endpoints = [get_users, get_user, create_user, update_user, delete_user]
        client.register_endpoints(endpoints)
        print(f"✓ Registered {len(endpoints)} endpoints")
        
        # Test: Get all users
        print("\n2. Testing get_users()...")
        try:
            get_users_method = client.get_client_method("get_users")
            users = await get_users_method()
            print(f"✓ Got {len(users)} users:")
            for user in users:
                print(f"  - {user['name']} ({user['id']})")
        except Exception as e:
            print(f"✗ Error: {e}")
        
        # Test: Get specific user
        print("\n3. Testing get_user(user_id=1)...")
        try:
            get_user_method = client.get_client_method("get_user")
            user = await get_user_method(user_id=1)
            print(f"✓ Got user: {user['name']} (ID: {user['id']}, Email: {user['email']})")
        except Exception as e:
            print(f"✗ Error: {e}")
        
        # Test: Create user
        print("\n4. Testing create_user()...")
        try:
            create_user_method = client.get_client_method("create_user")
            new_user = await create_user_method(
                name="Test User",
                email="test@example.com",
                age=25
            )
            print(f"✓ Created user: {new_user['name']} (ID: {new_user['id']})")
            new_user_id = new_user['id']
        except Exception as e:
            print(f"✗ Error: {e}")
            new_user_id = None
        
        # Test: Update user
        if new_user_id:
            print("\n5. Testing update_user()...")
            try:
                update_user_method = client.get_client_method("update_user")
                updated_user = await update_user_method(
                    user_id=new_user_id,
                    name="Updated Test User",
                    age=26
                )
                print(f"✓ Updated user: {updated_user['name']} (Age: {updated_user['age']})")
            except Exception as e:
                print(f"✗ Error: {e}")
            
            # Test: Delete user
            print("\n6. Testing delete_user()...")
            try:
                delete_user_method = client.get_client_method("delete_user")
                result = await delete_user_method(user_id=new_user_id)
                print(f"✓ {result['message']}")
            except Exception as e:
                print(f"✗ Error: {e}")
        
        # Test: Tools
        print("\n7. Testing tools generation...")
        tools = client.get_all_tools()
        print(f"✓ Generated {len(tools)} tools:")
        for tool in tools:
            print(f"  - {tool.name}")
        
        print("\n" + "=" * 70)
        print("✅ Client test complete!")
        print("=" * 70)
    
    asyncio.run(test_client())
