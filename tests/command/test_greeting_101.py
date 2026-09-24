# REQ-OPS-101
from src.command.greeting_101 import greet

def test_greet_returns_greeting():
    assert greet("Dario") == "Hello, Dario!"
