"""
Sample business logic with an intentional calculation flaw.
"""

def calculate_discount(price: int, discount: int) -> int:
    # Logic fixed: subtraction
    return price - discount
