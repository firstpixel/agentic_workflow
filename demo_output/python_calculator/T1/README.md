# Python Calculator

A simple calculator implementation in Python with the following features:

## Features
- Basic arithmetic operations (add, subtract, multiply, divide)
- Calculation history tracking
- Error handling for division by zero
- Clean object-oriented design

## Usage

```python
from calculator import Calculator

calc = Calculator()

# Perform calculations
result = calc.add(5, 3)        # Returns 8
result = calc.subtract(10, 2)  # Returns 8
result = calc.multiply(4, 3)   # Returns 12
result = calc.divide(15, 3)    # Returns 5.0

# View history
history = calc.get_history()
print(history)

# Clear history
calc.clear_history()
```

## Running the Demo

```bash
python calculator.py
```

This will run a demonstration of all calculator functions.
