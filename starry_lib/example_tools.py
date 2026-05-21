#!/usr/bin/env python3
"""
This script shows how to:
1. Define tools in model format
2. Send user messages with tools available
3. Handle tool calls from the assistant
4. Execute tools and return results
5. Get final responses after tool execution
"""

import json
import requests

API_ENDPOINT = "https://davy.labs.lenovo.com:5000/v1"
API_KEY = "quill"  # Replace with your actual API key
MODEL_NAME = "gpt-oss-120b-thinking"
CERT_FILE = "davy.labs.lenovo.com.crt"  # Certificate file for SSL verification


#!!!IMPORT!!!
#!!!IMPORT!!!
#!!!IMPORT!!!
#!!!IMPORT!!!
#This is where you define the tools the LLM can call (WHAT ACTUALLY EXECUTES on the machine running this script)!
#GIVE THE LLM LIMITED ACCESS SO WE DON'T HAVE AN AI UPRISING! SANITIZE INPUTS! ENSURE NO WAY TO ESCAPE OR WRITE OUTPUT OUTSIDE OF SAFE DIRECTORY!
def get_weather(location: str) -> dict:
    """
    Example tool function: Get weather for a location.
    In a real application, this would call an actual weather API.

    Args:
        location: City name to get weather for

    Returns:
        Dictionary with weather information
    """
    return {
        "location": location,
        "temperature": 22,
        "condition": "sunny"
    }

def calculate(expression: str) -> dict:
    """
    Example tool function: Calculate mathematical expressions.

    Args:
        expression: Math expression as a string (e.g., "2 + 2")

    Returns:
        Dictionary with calculation result or error
    """
    try:
        # IMPORTANT EXAMPLE Only allow safe math characters to prevent code injection
        if not all(c in "0123456789+-*/().% " for c in expression):
            return {"error": "Invalid characters in expression"}

        result = eval(expression)
        return {"expression": expression, "result": result}
    except Exception as e:
        return {"error": str(e)}

# Define available tools in OpenAI function calling format
# This tells the AI what tools are available and how to use them
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",           # Function name the AI will call
            "description": "Get weather for a location",  # What the function does
            "parameters": {                  # Function parameters in JSON Schema format
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City name"
                    }
                },
                "required": ["location"]     # Required parameters
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Calculate math expressions",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Math expression like '2 + 2'"
                    }
                },
                "required": ["expression"]
            }
        }
    }
]

# Map function names to actual Python functions
# This allows us to execute the functions when the AI calls them
FUNCTIONS = {
    "get_weather": get_weather,
    "calculate": calculate
}

def call_api(messages: list, tools: list = None) -> dict:
    """
    Make an API call to vLLM's OpenAI-compatible endpoint.

    Args:
        messages: List of conversation messages
        tools: Optional list of available tools

    Returns:
        API response as dictionary
    """
    # Prepare the request payload
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": 0.1              # Low temperature for consistent responses
    }

    # Add tools if provided (only needed for initial request)
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"  # Let the model decide when to use tools

    # Make the HTTP request with certificate verification
    response = requests.post(
        f"{API_ENDPOINT}/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json=payload,
        verify=CERT_FILE                # Use certificate file for SSL verification
    )

    return response.json()

def run_function(tool_call: dict) -> str:
    """
    Execute a function call requested by the AI.

    Args:
        tool_call: Tool call object from the AI response

    Returns:
        Function result as JSON string
    """
    # Extract function name and arguments from the tool call
    function_name = tool_call["function"]["name"]
    arguments = json.loads(tool_call["function"]["arguments"])

    # Look up and call the actual function
    function = FUNCTIONS[function_name]
    result = function(**arguments)

    # Return result as JSON string for the AI
    return json.dumps(result)

def chat_with_tools(user_input: str):
    """
    Main function demonstrating the complete tool calling flow.

    This shows the typical pattern:
    1. Send user message with tools available
    2. Check if AI wants to call any tools
    3. Execute requested tools
    4. Get final response from AI

    Args:
        user_input: The user's question or request
    """
    print(f"User: {user_input}")

    # Step 1: Send user message with tools available
    messages = [{"role": "user", "content": user_input}]
    response = call_api(messages, tools=TOOLS)

    # Check for API errors
    if "choices" not in response:
        print(f"API Error: {response}")
        return

    assistant_message = response["choices"][0]["message"]

    # Fix: Some models set content to None when making tool calls
    # vLLM expects content to be a string, so we use empty string
    if assistant_message.get("content") is None:
        assistant_message["content"] = ""

    messages.append(assistant_message)

    # Step 2: Check if assistant wants to call tools
    if "tool_calls" in assistant_message:
        print("🔧 Assistant is calling tools...")
        print(f"  assistant calling tool: {assistant_message}")

        # Step 3: Execute each tool call
        for tool_call in assistant_message["tool_calls"]:
            func_name = tool_call["function"]["name"]
            print(f"  → Calling {func_name}")

            # Run the function and get result
            result = run_function(tool_call)
            print(f"  → Result: {result}")

            # Add function result to conversation (Hermes format)
            # The tool_call_id links this result back to the original tool call
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": result
            })

        # Step 4: Get final response from assistant (no tools needed for final call)
        final_response = call_api(messages)
        if "choices" in final_response:
            final_message = final_response["choices"][0]["message"]["content"]
            print(f"Assistant: {final_message}")
        else:
            print(f"API Error: {final_response}")
            # Fallback: summarize the tool results
            print("Assistant: I called the tools and got the results above.")

    else:
        # No tools needed - direct response
        print(f"Assistant: {assistant_message['content']}")

def main():
    """
    Run example conversations to demonstrate tool use.

    This shows different scenarios:
    - Tool use (weather, math)
    - Regular conversation (no tools needed)
    """
    examples = [
        "What's the weather in Tokyo?",    # Should call get_weather
        "Calculate 25 * 4 + 10",          # Should call calculate
        "Hello there!"                    # Should respond normally
    ]

    for example in examples:
        print("\n" + "="*50)
        chat_with_tools(example)

if __name__ == "__main__":
    main()
